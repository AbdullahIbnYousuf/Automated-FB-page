from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anyio
import httpx
import pytest
from pydantic import SecretStr

from app.config import PublishMode, get_settings
from app.database import get_session_factory
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookWriteError, FacebookWriteErrorCode
from app.models.post import SchedulingMode
from app.services.errors import AppError
from app.services.facebook_scheduler import FacebookScheduler
from app.services.post_service import PostService
from app.services.scheduling_service import SchedulingService
from tests.helpers import image_bytes


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
    assert unauthenticated_client.post("/api/posts/unknown/schedule-video", json={}).status_code == 401


@pytest.fixture
def dashboard_live_video(monkeypatch):
    settings = get_settings()
    for key, value in {
        "publish_mode": PublishMode.FACEBOOK_SCHEDULE, "automation_enabled": True,
        "video_facebook_scheduling_enabled": True,
        "facebook_page_id": "1234", "facebook_page_access_token": SecretStr("fake-video-token"),
    }.items():
        monkeypatch.setattr(settings, key, value)
    return settings


def approval(record, **overrides):
    return {"confirmed": True, "reviewed_updated_at": record["updated_at"], "reviewed_page_id": "1234", **overrides}


@pytest.mark.parametrize("setting,value,code", [
    ("video_facebook_scheduling_enabled", False, "VIDEO_PUBLISHING_DISABLED"),
    ("automation_enabled", False, "PUBLISHING_DISABLED"),
    ("publish_mode", PublishMode.DRY_RUN, "PUBLISHING_DISABLED"),
    ("facebook_page_access_token", None, "FACEBOOK_CONFIGURATION_REQUIRED"),
])
def test_dashboard_live_gates_fail_closed(client, monkeypatch, make_video, dashboard_live_video, setting, value, code):
    def forbidden(*args, **kwargs):
        pytest.fail("disabled live scheduling reached Meta")

    monkeypatch.setattr(FacebookClient, "schedule_page_video", forbidden)
    draft = upload(client, make_video()).json()
    monkeypatch.setattr(dashboard_live_video, setting, value)
    assert client.get("/api/system/status").json()["video_scheduling_page_id"] is None
    response = client.post(f"/api/posts/{draft['id']}/schedule-video", json=approval(draft))
    assert response.status_code == 503 and response.json()["error"]["code"] == code
    assert client.get(f"/api/posts/{draft['id']}").json()["attempts"] == []


def test_dashboard_live_requires_exact_review_and_video(client, monkeypatch, make_video, dashboard_live_video):
    def forbidden(*args, **kwargs):
        pytest.fail("an unapproved draft reached Meta")

    monkeypatch.setattr(FacebookClient, "schedule_page_video", forbidden)
    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden)
    status = client.get("/api/system/status")
    assert status.json()["video_scheduling_page_id"] == "1234" and "fake-video-token" not in status.text
    draft = upload(client, make_video()).json()
    base = f"/api/posts/{draft['id']}"
    unconfirmed = client.post(f"{base}/schedule-video", json=approval(draft, confirmed=False))
    assert unconfirmed.json()["error"]["code"] == "VIDEO_APPROVAL_REQUIRED"
    assert client.post(f"{base}/schedule-video", json=approval(draft, confirmed="true")).status_code == 422
    wrong_page = client.post(f"{base}/schedule-video", json=approval(draft, reviewed_page_id="4321"))
    assert wrong_page.json()["error"]["code"] == "VIDEO_REVIEW_STALE"
    assert client.patch(base, json={"caption": "Edited after approval"}).status_code == 200
    stale = client.post(f"{base}/schedule-video", json=approval(draft))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VIDEO_REVIEW_STALE"
    assert client.get(base).json()["attempts"] == []
    # The original route must not bypass review even when the separate video gate is on.
    assert client.post(f"{base}/schedule").json()["error"]["code"] == "VIDEO_APPROVAL_REQUIRED"
    photo = client.post("/api/posts", data=fields(), files={"image": ("test.png", image_bytes("PNG"), "image/png")}).json()
    wrong_media = client.post(f"/api/posts/{photo['id']}/schedule-video", json=approval(photo))
    assert wrong_media.json()["error"]["code"] == "VIDEO_REQUIRED"


@pytest.mark.parametrize("unknown", [False, True])
def test_dashboard_schedules_reviewed_video_once_after_dry_run(client, monkeypatch, make_video, dashboard_live_video, unknown):
    clip = make_video()
    draft = upload(client, clip).json()
    base = f"/api/posts/{draft['id']}"
    requests = []

    async def meta(self, **kwargs):
        requests.append(kwargs)
        if unknown:
            raise FacebookWriteError(code=FacebookWriteErrorCode.OUTCOME_UNKNOWN, safe_message="Unknown fixture outcome", outcome_unknown=True)
        return "9414"

    monkeypatch.setattr(FacebookClient, "schedule_page_video", meta)
    dry_run = client.post(f"{base}/schedule?dry_run=true").json()
    assert dry_run["simulated"] and not dry_run["external_request_made"] and not requests
    record = client.get(base).json()
    confirmed = client.post(f"{base}/schedule-video", json=approval(record))
    persisted = client.get(base).json()
    repeat = client.post(f"{base}/schedule-video", json=approval(persisted))
    assert repeat.status_code == 409
    assert len(requests) == 1
    assert requests[0]["caption"] == record["caption"] and requests[0]["video_content"] == clip
    assert requests[0]["scheduled_publish_time"] == int(datetime.fromisoformat(record["scheduled_for_utc"]).timestamp())
    assert persisted["attempts"][0]["external_request_made"]
    if unknown:
        assert confirmed.status_code == 502 and repeat.json()["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
        assert persisted["facebook_object_id"] is None and persisted["status"] == "failed"
    else:
        assert confirmed.status_code == 200
        assert confirmed.json()["mode"] == "facebook_schedule" and not confirmed.json()["simulated"]
        assert persisted["facebook_object_id"] == "9414" and persisted["status"] == "scheduled"


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
