"""Dry-run scheduling state, attempt, and external-write safety tests."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import get_settings
from app.database import get_session_factory
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookWriteError, FacebookWriteErrorCode
from app.integrations.facebook.schemas import FacebookScheduledPhoto
from app.models.post import Post, PostStatus
from tests.conftest import InMemoryMediaService
from tests.helpers import create_post, future_local_time


def enable_facebook_scheduling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_MODE", "facebook_schedule")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "123456789012345")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "configured-test-page-token")
    get_settings.cache_clear()


def test_valid_dry_run_is_explicitly_simulated(client: TestClient) -> None:
    post = create_post(client).json()

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "dry_run"
    assert payload["simulated"] is True
    assert payload["success"] is True
    assert payload["external_request_made"] is False
    assert payload["post_status"] == "ready"
    assert "No request was sent to Facebook" in payload["message"]


def test_dry_run_never_marks_post_scheduled_or_adds_fake_facebook_id(
    client: TestClient,
) -> None:
    post = create_post(client).json()
    client.post(f"/api/posts/{post['id']}/schedule")

    persisted = client.get(f"/api/posts/{post['id']}").json()

    assert persisted["status"] == "ready"
    assert persisted["facebook_object_id"] is None
    assert persisted["attempts"][0]["result"] == "success"
    assert persisted["attempts"][0]["external_request_made"] is False


def test_automation_disabled_does_not_block_local_simulation(
    client: TestClient,
) -> None:
    assert get_settings().automation_enabled is False
    post = create_post(client).json()

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 200


def test_invalid_post_cannot_dry_run(client: TestClient) -> None:
    post = create_post(client).json()
    settings = get_settings()
    with get_session_factory(settings.require_database_url())() as session:
        session.execute(
            update(Post).where(Post.id == post["id"]).values(caption="")
        )
        session.commit()

    response = client.post(f"/api/posts/{post['id']}/schedule")
    persisted = client.get(f"/api/posts/{post['id']}").json()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CAPTION"
    assert persisted["status"] == "failed"
    assert persisted["attempts"][0]["result"] == "failed"


def test_missing_image_cannot_dry_run(
    client: TestClient, fake_media: InMemoryMediaService
) -> None:
    post = create_post(client).json()
    object_path = post["image_url"].removeprefix("/api/media/")
    fake_media.objects.pop(object_path)

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_IMAGE"
    persisted = client.get(f"/api/posts/{post['id']}").json()
    assert persisted["attempts"][0]["external_request_made"] is False


def test_running_attempt_is_rejected_as_duplicate(client: TestClient) -> None:
    post = create_post(client).json()
    settings = get_settings()
    with get_session_factory(settings.require_database_url())() as session:
        session.execute(
            update(Post)
            .where(Post.id == post["id"])
            .values(status=PostStatus.SCHEDULING)
        )
        session.commit()

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_ATTEMPT_RISK"


def test_dry_run_service_invokes_no_http_or_external_write_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = create_post(client).json()

    def forbidden_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise AssertionError("Dry run attempted an external HTTP request")

    async def forbidden_async_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise AssertionError("Dry run attempted an external HTTP request")

    monkeypatch.setattr(httpx, "request", forbidden_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_async_request)
    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 200
    assert response.json()["external_request_made"] is False


def test_non_dry_run_configuration_fails_closed_without_attempt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = create_post(client).json()
    monkeypatch.setenv("PUBLISH_MODE", "facebook_schedule")
    monkeypatch.setenv("AUTOMATION_ENABLED", "false")
    get_settings.cache_clear()

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PUBLISHING_DISABLED"
    persisted = client.get(f"/api/posts/{post['id']}").json()
    assert persisted["status"] == "draft"
    assert persisted["attempts"] == []


def test_automation_true_with_dry_run_still_makes_no_facebook_write(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOMATION_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_MODE", "dry_run")
    get_settings.cache_clear()
    calls = 0

    async def forbidden_write(self, **kwargs):  # type: ignore[no-untyped-def]
        del self, kwargs
        nonlocal calls
        calls += 1
        raise AssertionError("Dry run called Facebook")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden_write)
    post = create_post(client).json()
    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 200
    assert response.json()["mode"] == "dry_run"
    assert calls == 0


def test_enabled_real_mode_stores_confirmed_meta_identifier(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_facebook_scheduling(monkeypatch)
    observed: dict[str, object] = {}

    async def accepted(self, **kwargs):  # type: ignore[no-untyped-def]
        del self
        observed.update(kwargs)
        return FacebookScheduledPhoto(id="photo-123", post_id="page-123_post-456")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", accepted)
    post = create_post(client).json()
    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "facebook_schedule"
    assert payload["simulated"] is False
    assert payload["post_status"] == "scheduled"
    assert payload["external_request_made"] is True
    assert payload["facebook_object_id"] == "page-123_post-456"
    assert observed["image_mime_type"] == "image/png"
    assert isinstance(observed["image_content"], bytes)
    assert int(observed["scheduled_publish_time"]) < 100_000_000_000

    persisted = client.get(f"/api/posts/{post['id']}").json()
    assert persisted["status"] == "scheduled"
    assert persisted["facebook_object_id"] == "page-123_post-456"
    assert persisted["attempts"][0]["mode"] == "facebook_schedule"
    assert persisted["attempts"][0]["result"] == "success"
    assert persisted["attempts"][0]["external_request_made"] is True


def test_confirmed_meta_rejection_marks_failed_without_raw_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_facebook_scheduling(monkeypatch)

    async def rejected(self, **kwargs):  # type: ignore[no-untyped-def]
        del self, kwargs
        raise FacebookWriteError(
            code=FacebookWriteErrorCode.PERMISSION_DENIED,
            safe_message="The Page token cannot create posts for this Page.",
            meta_error_code=200,
        )

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", rejected)
    post = create_post(client).json()
    response = client.post(f"/api/posts/{post['id']}/schedule")
    persisted = client.get(f"/api/posts/{post['id']}").json()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "FACEBOOK_PERMISSION_DENIED"
    assert persisted["status"] == "failed"
    assert persisted["facebook_object_id"] is None
    assert persisted["attempts"][0]["external_request_made"] is True


def test_ambiguous_write_is_persisted_and_cannot_be_submitted_again(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_facebook_scheduling(monkeypatch)
    calls = 0

    async def ambiguous(self, **kwargs):  # type: ignore[no-untyped-def]
        del self, kwargs
        nonlocal calls
        calls += 1
        raise FacebookWriteError(
            code=FacebookWriteErrorCode.OUTCOME_UNKNOWN,
            safe_message=(
                "Facebook scheduling outcome is unknown. The request may have "
                "reached Meta; do not submit this post again until it is checked."
            ),
            outcome_unknown=True,
        )

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", ambiguous)
    post = create_post(client).json()
    first = client.post(f"/api/posts/{post['id']}/schedule")
    second = client.post(f"/api/posts/{post['id']}/schedule")
    persisted = client.get(f"/api/posts/{post['id']}").json()

    assert first.status_code == 502
    assert second.status_code == 409
    assert calls == 1
    assert persisted["status"] == "failed"
    assert persisted["last_error_code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    assert persisted["attempts"][0]["external_request_made"] is True
    assert len(persisted["attempts"]) == 1

    edit = client.patch(
        f"/api/posts/{post['id']}", json={"caption": "Unsafe reset attempt"}
    )
    assert edit.status_code == 409


@pytest.mark.parametrize(
    ("minutes", "expected_code"),
    [
        (9, "FACEBOOK_SCHEDULE_TOO_SOON"),
        (31 * 24 * 60, "FACEBOOK_SCHEDULE_TOO_FAR"),
    ],
)
def test_real_mode_enforces_current_meta_window_before_write(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    minutes: int,
    expected_code: str,
) -> None:
    enable_facebook_scheduling(monkeypatch)
    calls = 0

    async def forbidden_write(self, **kwargs):  # type: ignore[no-untyped-def]
        del self, kwargs
        nonlocal calls
        calls += 1
        raise AssertionError("Invalid time reached Facebook")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden_write)
    local_time = datetime.now(ZoneInfo("Asia/Dhaka")) + timedelta(minutes=minutes)
    post = create_post(
        client,
        scheduled_for_local=local_time.replace(second=0, microsecond=0).strftime(
            "%Y-%m-%dT%H:%M"
        ),
    ).json()
    response = client.post(f"/api/posts/{post['id']}/schedule")
    persisted = client.get(f"/api/posts/{post['id']}").json()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    assert calls == 0
    assert persisted["attempts"][0]["external_request_made"] is False


def test_already_scheduled_post_cannot_create_second_meta_write(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_facebook_scheduling(monkeypatch)
    calls = 0

    async def accepted(self, **kwargs):  # type: ignore[no-untyped-def]
        del self, kwargs
        nonlocal calls
        calls += 1
        return FacebookScheduledPhoto(id="photo-1", post_id="page_post-1")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", accepted)
    post = create_post(client, scheduled_for_local=future_local_time()).json()
    first = client.post(f"/api/posts/{post['id']}/schedule")
    second = client.post(f"/api/posts/{post['id']}/schedule")

    assert first.status_code == 200
    assert second.status_code == 409
    assert calls == 1
