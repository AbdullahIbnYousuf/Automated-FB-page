"""Protected API and secret-safety tests for Facebook Page connection."""

import asyncio
import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.dependencies import get_facebook_connection_service
from app.integrations.facebook.schemas import (
    FacebookConnectionState,
    FacebookConnectionStatus,
    FacebookPageIdentity,
)
from app.main import app
from app.integrations.facebook.errors import FacebookClientError
from app.services.facebook_connection_service import FacebookConnectionService


class StubFacebookConnectionService:
    def __init__(self, result: FacebookConnectionStatus) -> None:
        self.result = result
        self.test_calls = 0

    def get_status(self) -> FacebookConnectionStatus:
        return self.result

    async def test_connection(self) -> FacebookConnectionStatus:
        self.test_calls += 1
        return self.result


def connected_result() -> FacebookConnectionStatus:
    return FacebookConnectionStatus(
        connected=True,
        status=FacebookConnectionState.CONNECTED,
        page_id_configured=True,
        access_token_configured=True,
        page=FacebookPageIdentity(id="123456789012345", name="Example Page"),
        api_version="v26.0",
        message=(
            "Facebook Page connection verified. "
            "Publishing capability has not yet been proven."
        ),
        last_checked_at=datetime.now(UTC),
    )


def test_facebook_endpoints_require_operator_authentication(
    unauthenticated_client: TestClient,
) -> None:
    assert unauthenticated_client.get("/api/facebook/status").status_code == 401
    assert (
        unauthenticated_client.post("/api/facebook/test-connection").status_code
        == 401
    )


def test_missing_configuration_is_reported_safely(client: TestClient) -> None:
    response = client.get("/api/facebook/status")

    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "status": "not_configured",
        "page_id_configured": False,
        "access_token_configured": False,
        "page": None,
        "api_version": "v26.0",
        "message": "Facebook Page credentials are not fully configured.",
        "last_checked_at": None,
        "publishing_capability_verified": False,
    }


@pytest.mark.parametrize(
    ("page_id", "token", "expected_page", "expected_token"),
    [
        ("123456789012345", None, True, False),
        (None, "configured-token", False, True),
    ],
)
def test_partial_configuration_reports_the_missing_value(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    page_id: str | None,
    token: str | None,
    expected_page: bool,
    expected_token: bool,
) -> None:
    if page_id is not None:
        monkeypatch.setenv("FACEBOOK_PAGE_ID", page_id)
    if token is not None:
        monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", token)
    get_settings.cache_clear()
    get_facebook_connection_service.cache_clear()

    response = client.get("/api/facebook/status")

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"
    assert response.json()["page_id_configured"] is expected_page
    assert response.json()["access_token_configured"] is expected_token
    if page_id:
        assert page_id not in response.text
    if token:
        assert token not in response.text


def test_both_credentials_present_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    page_id = "123456789012345"
    token = "token-that-must-never-be-returned"
    monkeypatch.setenv("FACEBOOK_PAGE_ID", page_id)
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", token)
    get_settings.cache_clear()
    get_facebook_connection_service.cache_clear()

    response = client.get("/api/facebook/status")

    assert response.status_code == 200
    assert response.json()["status"] == "not_verified"
    assert response.json()["page_id_configured"] is True
    assert response.json()["access_token_configured"] is True
    assert page_id not in response.text
    assert token not in response.text


def test_authenticated_connection_test_returns_safe_page_identity(
    client: TestClient,
) -> None:
    stub = StubFacebookConnectionService(connected_result())
    app.dependency_overrides[get_facebook_connection_service] = lambda: stub

    response = client.post("/api/facebook/test-connection")

    assert response.status_code == 200
    assert response.json()["page"] == {
        "id": "123456789012345",
        "name": "Example Page",
    }
    assert response.json()["publishing_capability_verified"] is False
    assert stub.test_calls == 1


def test_raw_meta_error_and_token_never_reach_api_response(
    client: TestClient,
) -> None:
    token = "secret-page-token"
    raw_meta_error = "OAuthException raw diagnostic"
    result = FacebookConnectionStatus(
        connected=False,
        status=FacebookConnectionState.INVALID_CREDENTIALS,
        page_id_configured=True,
        access_token_configured=True,
        api_version="v26.0",
        message="Meta did not accept the Facebook Page access token.",
        last_checked_at=datetime.now(UTC),
    )
    stub = StubFacebookConnectionService(result)
    app.dependency_overrides[get_facebook_connection_service] = lambda: stub

    response = client.post("/api/facebook/test-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "invalid_credentials"
    assert token not in response.text
    assert raw_meta_error not in response.text


def test_token_and_raw_error_cause_never_reach_captured_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "captured-log-secret-token"
    raw_meta_error = "raw Meta diagnostic that must stay private"
    settings = Settings(
        facebook_page_id="123456789012345",
        facebook_page_access_token=token,
    )

    class FailingClient:
        async def get_page_identity(self):  # type: ignore[no-untyped-def]
            try:
                raise RuntimeError(f"{raw_meta_error}: {token}")
            except RuntimeError as cause:
                raise FacebookClientError(
                    state=FacebookConnectionState.INVALID_CREDENTIALS,
                    safe_message="Meta did not accept the Facebook Page access token.",
                    meta_error_code=190,
                ) from cause

    service = FacebookConnectionService(settings, FailingClient())  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(service.test_connection())

    assert result.status is FacebookConnectionState.INVALID_CREDENTIALS
    assert token not in caplog.text
    assert raw_meta_error not in caplog.text
