"""Phase 1 API and configuration-safety tests."""

from fastapi.testclient import TestClient

from app.config import get_settings
import pytest


def test_health_endpoint_responds_successfully(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "facebook-page-operations-dashboard",
    }


def test_system_status_endpoint_responds_successfully(client: TestClient) -> None:
    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Dhaka"


def test_system_status_uses_safe_publishing_defaults(client: TestClient) -> None:
    payload = client.get("/api/system/status").json()

    assert payload["publish_mode"] == "dry_run"
    assert payload["automation_enabled"] is False
    assert payload["publishing_enabled"] is False


def test_system_status_reports_credential_presence_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    page_id = "page-id-that-must-not-be-returned"
    token = "token-that-must-never-be-returned"
    monkeypatch.setenv("FACEBOOK_PAGE_ID", page_id)
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", token)
    get_settings.cache_clear()

    response = client.get("/api/system/status")

    assert response.status_code == 200
    payload = response.json()
    serialized_payload = response.text
    assert payload["facebook"] == {
        "page_id_configured": True,
        "access_token_configured": True,
        "fully_configured": True,
    }
    assert page_id not in serialized_payload
    assert token not in serialized_payload
    assert "facebook_page_access_token" not in serialized_payload
