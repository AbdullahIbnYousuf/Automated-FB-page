from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anyio
import httpx
import pytest
from pydantic import SecretStr

from app.config import PublishMode, get_settings
from app.database import get_session_factory
from app.integrations.facebook.client import FacebookClient
from app.models.post import SchedulingMode
from app.services.errors import AppError
from app.services.facebook_scheduler import FacebookScheduler
from app.services.post_service import PostService
from app.services.scheduling_service import SchedulingService


def fields():
    local_time = datetime.now(ZoneInfo("Asia/Dhaka")) + timedelta(hours=1)
    return {"caption": "A private video smoke test", "scheduled_for_local": local_time.strftime("%Y-%m-%dT%H:%M"), "timezone": "Asia/Dhaka"}


def upload(client, content, name="test.mp4", mime="video/mp4"):
    return client.post("/api/posts/video", data=fields(), files={"video": (name, content, mime)})


def test_actual_mp4_upload_playback_and_dry_run(client, fake_media, make_video):
    clip = make_video()
    draft = upload(client, clip)
    assert draft.status_code == 201, draft.text
    record = draft.json()
    assert record["status"] == "draft" and record["image_url"] is None
    assert record["video_url"].endswith(".mp4")
    assert client.get(f"/api/posts/{record['id']}").json()["video_url"] == record["video_url"]
    media = client.get(record["video_url"])
    assert media.headers["content-type"] == "video/mp4"
    assert media.headers["cache-control"] == "private, no-store"
    assert media.content == clip
    result = client.post(f"/api/posts/{record['id']}/schedule?dry_run=true").json()
    assert result["simulated"] and not result["external_request_made"]
    assert result["facebook_object_id"] is None and result["post_status"] == "ready"
    assert len(fake_media.objects) == 1


def test_rejects_invalid_wrong_codec_and_oversized_videos(client, fake_media, make_video):
    assert upload(client, b"not video").json()["error"]["code"] == "INVALID_VIDEO"
    assert upload(client, make_video(codec="mpeg4")).json()["error"]["code"] == "INVALID_VIDEO"
    clip = make_video()
    assert upload(client, clip[:-35]).json()["error"]["code"] == "INVALID_VIDEO"
    assert upload(client, clip, "test.png").json()["error"]["code"] == "UNSUPPORTED_VIDEO"
    limit = get_settings().max_video_upload_bytes
    chunked = client.post("/api/posts/video", data=iter([b"x" * (limit + 65537)]), headers={"content-type": "multipart/form-data; boundary=probe"})
    assert chunked.status_code == 413
    assert upload(client, b"x" * (limit + 1)).status_code == 413
    assert len(fake_media.objects) == 0


def test_upload_and_video_preview_require_authentication(unauthenticated_client, make_video):
    assert upload(unauthenticated_client, make_video()).status_code == 401
    assert unauthenticated_client.get("/api/media/posts/01234567-0000-4000-8000-0123456789ab.mp4").status_code == 401


@pytest.mark.parametrize("upstream_status,outcome", [(200, "scheduled"), (502, "unknown")])
def test_real_video_guards_and_one_meta_request(client, fake_media, make_video, upstream_status, outcome):
    clip = make_video()
    post_id = upload(client, clip).json()["id"]
    settings = get_settings().model_copy(update={
        "publish_mode": PublishMode.FACEBOOK_SCHEDULE, "automation_enabled": True,
        "facebook_page_id": "1234", "facebook_page_access_token": SecretStr("token-for-test"),
    })
    requests = []

    def meta(request):
        requests.append(request)
        assert request.url == "https://graph.facebook.com/v26.0/1234/videos"
        assert request.headers["Authorization"] == "Bearer token-for-test"
        for piece in (b'name="description"', b'A private video smoke test', b'name="published"\r\n\r\nfalse',
                      b'name="scheduled_publish_time"', b'name="unpublished_content_type"\r\n\r\nSCHEDULED', b'name="source"', clip):
            assert piece in request.content
        return httpx.Response(upstream_status, json={"id": "9414"} if upstream_status == 200 else {})

    def run(cfg, confirmed):
        async def schedule():
            with get_session_factory(cfg.require_database_url())() as session:
                service = SchedulingService(session, cfg, media_service=fake_media, facebook_scheduler=FacebookScheduler(FacebookClient(cfg, transport=httpx.MockTransport(meta))))
                return await service.schedule_post(post_id, requested_mode=SchedulingMode.FACEBOOK_SCHEDULE, video_confirmed=confirmed)
        return anyio.run(schedule)

    with pytest.raises(AppError) as disabled:
        run(settings, True)
    assert disabled.value.code == "VIDEO_PUBLISHING_DISABLED"
    settings.video_facebook_scheduling_enabled = True
    with pytest.raises(AppError) as not_confirmed:
        run(settings, False)
    assert not_confirmed.value.code == "VIDEO_APPROVAL_REQUIRED"
    assert not requests

    if outcome == "scheduled":
        assert run(settings, True).facebook_object_id == "9414"
    else:
        for _ in range(2):
            with pytest.raises(AppError) as unknown:
                run(settings, True)
            assert unknown.value.code == "FACEBOOK_OUTCOME_UNKNOWN"
    assert len(requests) == 1
    with get_session_factory(settings.require_database_url())() as session:
        post = PostService(session, settings).get_post(post_id)
        assert post.attempts[0].external_request_made
        assert post.status.value == ("scheduled" if outcome == "scheduled" else "failed")
