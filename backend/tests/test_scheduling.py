"""Dry-run scheduling state, attempt, and external-write safety tests."""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import get_settings
from app.database import get_session_factory
from app.models.post import Post, PostStatus
from tests.conftest import InMemoryMediaService
from tests.helpers import create_post


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
    monkeypatch.setenv("AUTOMATION_ENABLED", "true")
    get_settings.cache_clear()

    response = client.post(f"/api/posts/{post['id']}/schedule")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONFIGURATION_ERROR"
    persisted = client.get(f"/api/posts/{post['id']}").json()
    assert persisted["status"] == "draft"
    assert persisted["attempts"] == []
