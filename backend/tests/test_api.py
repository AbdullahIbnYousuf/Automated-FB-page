"""Phase 1 API and configuration-safety tests."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies import get_auth_service
from app.main import app
from app.services.errors import AppError
import pytest


def test_health_endpoint_responds_successfully(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "facebook-page-operations-dashboard",
    }


def test_public_health_does_not_require_authentication(
    unauthenticated_client: TestClient,
) -> None:
    assert unauthenticated_client.get("/api/health").status_code == 200


def test_protected_endpoint_rejects_missing_token(
    unauthenticated_client: TestClient,
) -> None:
    response = unauthenticated_client.get("/api/system/status")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_protected_endpoint_rejects_invalid_token(
    unauthenticated_client: TestClient,
) -> None:
    class RejectingAuthService:
        async def authenticate(self, access_token: str):  # type: ignore[no-untyped-def]
            del access_token
            raise AppError(
                code="AUTH_REQUIRED",
                message="Sign in with the authorized operator account.",
                status_code=401,
            )

    app.dependency_overrides[get_auth_service] = RejectingAuthService
    response = unauthenticated_client.get(
        "/api/system/status", headers={"Authorization": "Bearer invalid"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_mocked_valid_authenticated_request_is_accepted(
    unauthenticated_client: TestClient,
) -> None:
    class AcceptingAuthService:
        async def authenticate(self, access_token: str):  # type: ignore[no-untyped-def]
            assert access_token == "valid-test-token"
            from app.services.auth_service import AuthenticatedOperator

            return AuthenticatedOperator(
                id="operator-id", email="operator@example.com"
            )

    app.dependency_overrides[get_auth_service] = AcceptingAuthService
    response = unauthenticated_client.get(
        "/api/system/status",
        headers={"Authorization": "Bearer valid-test-token"},
    )

    assert response.status_code == 200
    assert response.json()["authentication_required"] is True


def test_posts_are_not_public(unauthenticated_client: TestClient) -> None:
    response = unauthenticated_client.get("/api/posts")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


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
    assert "test-secret-key" not in serialized_payload
    assert "database_url" not in serialized_payload
