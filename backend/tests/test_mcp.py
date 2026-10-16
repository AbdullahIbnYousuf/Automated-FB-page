"""Authenticated MCP HTTP protocol and business-flow tests, with isolated storage/Meta."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO

import anyio
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import UploadFile
from PIL import Image
from pydantic import SecretStr

from app.config import PublishMode, get_settings
from app.database import get_session_factory
from app.main import mcp_host
from app.mcp.auth import SupabaseTokenVerifier
from app.mcp.files import ChatGPTFile, ChatGPTFileDownloader
from app.mcp.schemas import CreatePostInput
from app.models.post import Post
from app.services.errors import AppError


def png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


def token(key, **overrides) -> str:
    settings = get_settings()
    claims = {
        "iss": settings.mcp_issuer_url, "aud": settings.mcp_resource_url,
        "sub": "operator-id", "email": "operator@example.com", "client_id": "chatgpt-client",
        "scope": "email", "role": "authenticated", "is_anonymous": False,
        "iat": int(time.time()) - 1, "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "test-key"})


@pytest.fixture
def mcp_client(unauthenticated_client, fake_media, signing_key, monkeypatch):
    jwk = jwt.PyJWK.from_dict(json.loads(jwt.algorithms.ECAlgorithm.to_jwk(signing_key.public_key())))

    async def key(self, kid):
        return jwk if kid == "test-key" else None

    monkeypatch.setattr(SupabaseTokenVerifier, "_key", key)
    mcp_host.tools.media = fake_media

    async def download(file):
        return UploadFile(file=BytesIO(png()), filename="test.png", headers={"content-type": "image/png"})

    monkeypatch.setattr(mcp_host.tools.downloader, "download", download)
    unauthenticated_client.headers.update({
        "Authorization": f"Bearer {token(signing_key)}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    })
    return unauthenticated_client


def rpc(client, method: str, params=None):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, name: str, args=None) -> dict:
    response = rpc(client, "tools/call", {"name": name, "arguments": args or {}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "result" in body, body
    result = body["result"]
    assert result["isError"] is not result["structuredContent"]["ok"]
    return result["structuredContent"]


def create_args(key="first-request-001") -> dict:
    return {
        "caption": "A prepared test caption", "request_key": key,
        "scheduled_for_local": (datetime.now(UTC) + timedelta(hours=8)).replace(tzinfo=None).isoformat(timespec="minutes"),
        "image": {"download_url": "https://files.oaiusercontent.com/test?secret=signed-value", "file_id": "file-test"},
    }


def test_mcp_oauth_metadata_and_missing_token(unauthenticated_client):
    metadata = unauthenticated_client.get("/.well-known/oauth-protected-resource/mcp")
    assert metadata.status_code == 200
    assert metadata.json()["resource"] == get_settings().mcp_resource_url
    assert metadata.json()["authorization_servers"] == [get_settings().mcp_issuer_url]
    response = rpc(unauthenticated_client, "tools/list")
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
    assert "test-secret-key" not in response.text


@pytest.mark.parametrize("overrides", [
    {"exp": 1}, {"aud": "authenticated"}, {"email": "someone@example.com"},
    {"iss": "https://evil.example/auth/v1"}, {"client_id": ""}, {"scope": "profile"},
    {"is_anonymous": True}, {"role": "service_role"},
])
def test_invalid_oauth_claims_rejected(mcp_client, signing_key, overrides):
    mcp_client.headers["Authorization"] = f"Bearer {token(signing_key, **overrides)}"
    assert rpc(mcp_client, "tools/list").status_code == 401


def test_wrong_signature_rejected(mcp_client):
    mcp_client.headers["Authorization"] = f"Bearer {token(ec.generate_private_key(ec.SECP256R1()))}"
    assert rpc(mcp_client, "tools/list").status_code == 401


def test_initialize_discovery_file_schema_and_all_tools(mcp_client):
    result = rpc(mcp_client, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert result.status_code == 200
    assert result.json()["result"]["serverInfo"]["name"] == "The Test Lab Operations"
    response = rpc(mcp_client, "tools/list")
    tools = response.json()["result"]["tools"]
    assert len(tools) == 8
    for descriptor in tools:
        assert descriptor["_meta"]["securitySchemes"] == [{"type": "oauth2", "scopes": ["email"]}]
        assert "outputSchema" in descriptor
        if descriptor["name"] in {"create_post", "create_and_schedule_post"}:
            assert descriptor["_meta"]["openai/fileParams"] == ["image"]
            file_schema = descriptor["inputSchema"]["$defs"]["ChatGPTFile"]
            assert set(file_schema["properties"]) == {"download_url", "file_id", "mime_type", "file_name"}
            assert set(file_schema["required"]) == {"download_url", "file_id"}
            assert all(p["type"] == "string" for p in file_schema["properties"].values())
    assert call(mcp_client, "get_system_status")["data"]["publishing_enabled"] is False
    assert call(mcp_client, "test_facebook_connection")["data"]["status"] == "not_configured"


def test_all_post_tools_dry_run_and_replay(mcp_client, fake_media):
    args = create_args()
    draft = call(mcp_client, "create_post", args)
    assert draft["ok"] and draft["data"]["status"] == "draft"
    post_id = draft["data"]["id"]
    changed_url = {**args, "image": {**args["image"], "download_url": "https://files.oaiusercontent.com/refreshed"}}
    replay = call(mcp_client, "create_post", changed_url)
    assert replay["replayed"] and replay["data"]["id"] == post_id
    assert len(fake_media.objects) == 1
    assert call(mcp_client, "list_posts")["data"]["total"] == 1
    assert call(mcp_client, "get_post", {"post_id": post_id})["data"]["id"] == post_id
    assert call(mcp_client, "update_post", {"post_id": post_id, "caption": "Updated"})["data"]["caption"] == "Updated"
    result = call(mcp_client, "schedule_post", {"post_id": post_id})
    assert result["data"]["simulated"] is True
    assert result["data"]["external_request_made"] is False
    combined = call(mcp_client, "create_and_schedule_post", create_args("second-request-002"))
    assert combined["data"]["post"]["status"] == "ready"
    assert combined["data"]["schedule"]["simulated"] is True
    again = call(mcp_client, "create_and_schedule_post", create_args("second-request-002"))
    assert again["replayed"]
    history = call(mcp_client, "get_post", {"post_id": combined["data"]["post"]["id"]})
    assert len(history["data"]["attempts"]) == 1


def test_real_mode_is_never_silently_simulated(mcp_client):
    args = {**create_args(), "mode": "facebook_schedule"}
    response = call(mcp_client, "create_and_schedule_post", args)
    assert response["error"]["code"] == "PUBLISHING_DISABLED"
    assert call(mcp_client, "list_posts")["data"]["total"] == 0


def test_request_key_conflict_validation_and_pagination(mcp_client):
    args = create_args()
    assert call(mcp_client, "create_post", args)["ok"]
    conflict = call(mcp_client, "create_post", {**args, "caption": "Different"})
    assert conflict["error"]["code"] == "REQUEST_KEY_CONFLICT"
    invalid = call(mcp_client, "create_post", {**create_args("invalid-time-003"), "scheduled_for_local": "2000-01-01T12:00"})
    assert invalid["error"]["code"] == "INVALID_SCHEDULE"
    assert "signed-value" not in json.dumps(invalid)
    assert call(mcp_client, "list_posts", {"limit": 101})["error"]["code"] == "VALIDATION_ERROR"
    assert call(mcp_client, "list_posts", {"status": "scheduled"})["data"]["total"] == 0


def test_in_progress_request_does_not_create_second_post(mcp_client):
    args = create_args()
    with get_session_factory(get_settings().require_database_url())() as session:
        mcp_host.tools._reserve(session, "operator-id", "create_post", CreatePostInput.model_validate(args))
    response = call(mcp_client, "create_post", args)
    assert response["error"]["code"] == "OPERATION_IN_PROGRESS"
    assert call(mcp_client, "list_posts")["data"]["total"] == 0


def test_composite_ambiguous_meta_outcome_is_not_retried(mcp_client, monkeypatch):
    from app.integrations.facebook.errors import FacebookWriteError, FacebookWriteErrorCode

    count = 0

    async def uncertain(self, **kwargs):
        nonlocal count
        count += 1
        raise FacebookWriteError(code=FacebookWriteErrorCode.OUTCOME_UNKNOWN, safe_message="Unknown outcome; inspect Meta.", outcome_unknown=True)

    monkeypatch.setattr("app.integrations.facebook.client.FacebookClient.schedule_page_photo", uncertain)
    settings = mcp_host.tools.settings.model_copy(update={
        "automation_enabled": True, "publish_mode": PublishMode.FACEBOOK_SCHEDULE,
        "facebook_page_id": "123456", "facebook_page_access_token": SecretStr("test-token"),
    })
    mcp_host.tools.settings = settings
    args = {**create_args(), "mode": "facebook_schedule"}
    result = call(mcp_client, "create_and_schedule_post", args)
    assert result["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    post_id = result["error"]["post_id"]
    assert post_id
    assert call(mcp_client, "create_and_schedule_post", args)["replayed"]
    assert count == 1
    assert call(mcp_client, "schedule_post", {"post_id": post_id, "mode": "facebook_schedule"})["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    assert call(mcp_client, "update_post", {"post_id": post_id, "caption": "Retry"})["error"]["code"] == "INVALID_POST_STATE"


def test_download_with_missing_optional_metadata_and_no_credentials(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 443))])

    def handle(request):
        assert "authorization" not in request.headers
        assert "apikey" not in request.headers
        return httpx.Response(200, content=png(), headers={"content-type": "image/png"})

    downloader = ChatGPTFileDownloader(settings, transport=httpx.MockTransport(handle))
    upload = anyio.run(downloader.download, ChatGPTFile(download_url="https://files.oaiusercontent.com/file?sig=private", file_id="file-1"))
    assert upload.filename == "chatgpt-image.png"
    assert upload.content_type == "image/png"


@pytest.mark.parametrize("url", [
    "http://files.oaiusercontent.com/file", "https://127.0.0.1/image",
    "https://files.oaiusercontent.com.evil.example/image", "https://files.oaiusercontent.com:8443/image",
    "https://user:password@files.oaiusercontent.com/image",
])
def test_file_url_rejections(url):
    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(lambda r: pytest.fail("No request allowed")))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url=url, file_id="file-1"))
    assert error.value.code == "FILE_URL_NOT_ALLOWED"


@pytest.mark.parametrize("status,content,headers,code", [
    (403, b"Expired", {}, "FILE_UNAVAILABLE"),
    (200, b"invalid", {}, "INVALID_IMAGE"),
    (200, b"x" * 1025, {}, "IMAGE_TOO_LARGE"),
    (302, b"", {"location": "https://127.0.0.1/private"}, "FILE_URL_NOT_ALLOWED"),
])
def test_failed_image_downloads(monkeypatch, status, content, headers, code):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 443))])
    downloader = ChatGPTFileDownloader(get_settings().model_copy(update={"max_upload_bytes": 1024}), transport=httpx.MockTransport(lambda r: httpx.Response(status, content=content, headers=headers)))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url="https://files.oaiusercontent.com/file", file_id="file-1"))
    assert error.value.code == code


def test_concurrent_creation_has_one_post_and_image(mcp_client, fake_media):
    args = create_args()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call, mcp_client, "create_post", args) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert any(r["ok"] for r in results)
    assert all(r["ok"] or r["error"]["code"] == "OPERATION_IN_PROGRESS" for r in results)
    assert call(mcp_client, "list_posts")["data"]["total"] == 1
    assert len(fake_media.objects) == 1


def test_explicit_dry_run_remains_dry_run_when_real_enabled(mcp_client):
    mcp_host.tools.settings = mcp_host.tools.settings.model_copy(update={
        "automation_enabled": True, "publish_mode": PublishMode.FACEBOOK_SCHEDULE,
    })
    response = call(mcp_client, "create_and_schedule_post", create_args())
    assert response["ok"]
    assert response["data"]["schedule"]["simulated"] is True
    assert response["data"]["schedule"]["external_request_made"] is False


def test_normal_cancellation_records_the_real_write_outcome(client, fake_media):
    from app.services.scheduling_service import SchedulingService
    from tests.helpers import create_post

    post_id = create_post(client).json()["id"]
    settings = get_settings().model_copy(update={
        "automation_enabled": True, "publish_mode": PublishMode.FACEBOOK_SCHEDULE,
    })

    async def exercise():
        completed = []
        with anyio.CancelScope() as scope:
            class FakeScheduler:
                def prepare(self, post, image):
                    return object()

                async def execute(self, command):
                    scope.cancel()
                    await anyio.sleep(0)
                    from app.services.facebook_scheduler import FacebookScheduleResult
                    return FacebookScheduleResult(facebook_object_id="page_photo")

            with get_session_factory(settings.require_database_url())() as session:
                result = await SchedulingService(
                    session, settings, media_service=fake_media, facebook_scheduler=FakeScheduler(),
                ).schedule_post(post_id)
                completed.append(result)
        assert completed and completed[0].post_status == "scheduled"

    anyio.run(exercise)
    with get_session_factory(settings.require_database_url())() as session:
        post = session.get(Post, post_id)
        assert post.status == "scheduled"
        assert post.facebook_object_id == "page_photo"


def test_private_dns_answer_is_blocked_even_for_allowed_host(monkeypatch):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("10.0.0.1", 443))])
    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(lambda r: pytest.fail("Private network must not be contacted")))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url="https://files.oaiusercontent.com/file", file_id="file-1"))
    assert error.value.code == "FILE_URL_NOT_ALLOWED"


def test_current_protocol_tools_call_and_bad_origin(mcp_client):
    headers = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/call", "Mcp-Name": "get_system_status"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "get_system_status", "arguments": {},
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}},
    }}
    response = mcp_client.post("/mcp", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["structuredContent"]["ok"] is True
    bad = mcp_client.post("/mcp", headers={**headers, "Origin": "https://evil.example"}, json=body)
    assert bad.status_code == 403
