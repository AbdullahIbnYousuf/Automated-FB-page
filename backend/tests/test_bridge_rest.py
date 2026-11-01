"""Exercise bridge denial through real REST auth dependencies, not auth overrides."""

import httpx
import jwt
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.database import get_session_factory
from app.models.post import Post
from tests.helpers import create_post


def rest_token(client_id=None):
    claims = {"sub": "operator-id", "aud": "authenticated"}
    if client_id is not None:
        claims["client_id"] = client_id
    return jwt.encode(claims, "fixture-only-key-at-least-32-bytes-long", algorithm="HS256")


@pytest.fixture
def provider(monkeypatch):
    calls = []

    async def get(self, url, **kwargs):
        assert url == "https://example.supabase.co/auth/v1/user"
        calls.append(kwargs["headers"]["Authorization"])
        return httpx.Response(200, json={"id": "operator-id", "email": "operator@example.com"})

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    monkeypatch.setattr(get_settings(), "mcp_bridge_client_id", "bridge-client")
    return calls


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/system/status"),
    ("GET", "/api/facebook/status"),
    ("POST", "/api/facebook/test-connection"),
    ("GET", "/api/posts"),
    ("POST", "/api/posts"),
    ("GET", "/api/posts/unused"),
    ("PATCH", "/api/posts/unused"),
    ("POST", "/api/posts/unused/schedule"),
    ("GET", "/api/media/posts/00000000-0000-4000-8000-000000000001.png"),
])
def test_bridge_denied_on_every_operational_rest_route(
    unauthenticated_client, provider, fake_media, method, path,
):
    access_token = rest_token("bridge-client")
    response = unauthenticated_client.request(
        method, path, headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BRIDGE_REST_FORBIDDEN"
    assert provider == [f"Bearer {access_token}"]
    assert not fake_media.objects
    with get_session_factory(get_settings().require_database_url())() as session:
        assert session.scalar(select(func.count()).select_from(Post)) == 0


@pytest.mark.parametrize("client_id", [None, "existing-oauth-client", "bridge-client-other"])
def test_dashboard_and_other_clients_keep_rest_workflow(unauthenticated_client, provider, client_id):
    unauthenticated_client.headers["Authorization"] = f"Bearer {rest_token(client_id)}"
    status = unauthenticated_client.get("/api/system/status")
    assert status.status_code == 200
    assert status.json()["bridge_client_restricted"] is False
    post = create_post(unauthenticated_client)
    assert post.status_code == 201
    post_id = post.json()["id"]
    edited = unauthenticated_client.patch(f"/api/posts/{post_id}", json={"caption": "Edited draft"})
    assert edited.status_code == 200
    assert edited.json()["caption"] == "Edited draft"
    assert unauthenticated_client.get(post.json()["image_url"]).status_code == 200
    result = unauthenticated_client.post(f"/api/posts/{post_id}/schedule")
    assert result.status_code == 200 and result.json()["simulated"] is True
    assert result.json()["external_request_made"] is False


def test_provider_rejection_precedes_bridge_claim_inspection(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mcp_bridge_client_id", "bridge-client")

    async def reject(self, url, **kwargs):
        return httpx.Response(401, json={"message": "invalid token"})

    monkeypatch.setattr(httpx.AsyncClient, "get", reject)
    response = unauthenticated_client.get(
        "/api/system/status", headers={"Authorization": f"Bearer {rest_token('bridge-client')}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_wrong_operator_is_still_denied_with_bridge_configured(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mcp_bridge_client_id", "bridge-client")

    async def wrong_operator(self, url, **kwargs):
        return httpx.Response(200, json={"id": "other-id", "email": "other@example.com"})

    monkeypatch.setattr(httpx.AsyncClient, "get", wrong_operator)
    response = unauthenticated_client.get(
        "/api/system/status", headers={"Authorization": f"Bearer {rest_token()}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "OPERATOR_FORBIDDEN"
