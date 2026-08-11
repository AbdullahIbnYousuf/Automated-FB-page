"""Mocked tests for the read-only official Meta Graph API boundary."""

import asyncio

import httpx
import pytest

from app.config import Settings
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookClientError
from app.integrations.facebook.schemas import FacebookConnectionState


PAGE_ID = "123456789012345"
PAGE_TOKEN = "test-page-token-that-must-stay-secret"


def facebook_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "facebook_graph_api_version": "v26.0",
        "facebook_page_id": PAGE_ID,
        "facebook_page_access_token": PAGE_TOKEN,
        "facebook_request_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_success_uses_one_read_only_page_identity_request() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"id": PAGE_ID, "name": "Example Page"})

    page = asyncio.run(
        FacebookClient(
            facebook_settings(), transport=httpx.MockTransport(handler)
        ).get_page_identity()
    )

    assert page.model_dump() == {"id": PAGE_ID, "name": "Example Page"}
    assert len(observed) == 1
    request = observed[0]
    assert request.method == "GET"
    assert request.url.path == f"/v26.0/{PAGE_ID}"
    assert dict(request.url.params) == {"fields": "id,name"}
    assert request.headers["Authorization"] == f"Bearer {PAGE_TOKEN}"
    assert PAGE_TOKEN not in str(request.url)
    assert request.content == b""


@pytest.mark.parametrize(
    ("payload", "expected_state"),
    [
        (
            {"error": {"code": 190, "message": "raw invalid token detail"}},
            FacebookConnectionState.INVALID_CREDENTIALS,
        ),
        (
            {
                "error": {
                    "code": 190,
                    "error_subcode": 463,
                    "message": "raw expired token detail",
                }
            },
            FacebookConnectionState.EXPIRED_CREDENTIALS,
        ),
        (
            {"error": {"code": 200, "message": "raw permission detail"}},
            FacebookConnectionState.INSUFFICIENT_ACCESS,
        ),
        (
            {"error": {"code": 100, "message": "raw page detail"}},
            FacebookConnectionState.PAGE_INACCESSIBLE,
        ),
    ],
)
def test_known_meta_errors_are_classified_without_raw_messages(
    payload: dict[str, object],
    expected_state: FacebookConnectionState,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json=payload, request=request)
    )

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(), transport=transport
            ).get_page_identity()
        )

    assert caught.value.state is expected_state
    assert "raw" not in caught.value.safe_message
    assert PAGE_TOKEN not in caught.value.safe_message


def test_page_mismatch_is_rejected() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"id": "999999999999999", "name": "Wrong Page"},
            request=request,
        )
    )

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(), transport=transport
            ).get_page_identity()
        )

    assert caught.value.state is FacebookConnectionState.PAGE_MISMATCH


def test_meta_server_error_is_sanitized() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            503,
            json={"error": {"message": "internal raw Meta failure"}},
            request=request,
        )
    )

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(), transport=transport
            ).get_page_identity()
        )

    assert caught.value.state is FacebookConnectionState.META_UNAVAILABLE
    assert "internal raw" not in caught.value.safe_message


def test_timeout_is_sanitized() -> None:
    async def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-bearing debug detail", request=request)

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(), transport=httpx.MockTransport(timeout)
            ).get_page_identity()
        )

    assert caught.value.state is FacebookConnectionState.META_UNAVAILABLE
    assert "secret-bearing" not in caught.value.safe_message


@pytest.mark.parametrize(
    "payload",
    [{}, {"id": PAGE_ID}, {"id": PAGE_ID, "name": ""}, [PAGE_ID, "Page"]],
)
def test_malformed_page_response_is_rejected(payload: object) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload, request=request)
    )

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(), transport=transport
            ).get_page_identity()
        )

    assert caught.value.state is FacebookConnectionState.MALFORMED_RESPONSE


def test_invalid_page_configuration_makes_no_request() -> None:
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, request=request)

    with pytest.raises(FacebookClientError) as caught:
        asyncio.run(
            FacebookClient(
                facebook_settings(facebook_page_id="not-a-page-id"),
                transport=httpx.MockTransport(handler),
            ).get_page_identity()
        )

    assert caught.value.state is FacebookConnectionState.INVALID_CONFIGURATION
    assert called is False
