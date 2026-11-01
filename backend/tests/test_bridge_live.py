"""Bridge live capability tests over authenticated MCP HTTP; Meta is always mocked."""

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from threading import Event

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr, ValidationError

from app.config import PublishMode, Settings, get_settings
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookWriteError, FacebookWriteErrorCode
from app.integrations.facebook.schemas import FacebookScheduledPhoto
from app.main import mcp_host
from app.services.media_service import StoredObject
from tests.helpers import corrupt_image_bytes
from tests.test_mcp import call, create_args, mcp_client, rpc, signing_key, token


def enable_live(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_bridge_client_id", "chatgpt-client")
    monkeypatch.setattr(settings, "mcp_bridge_allow_live_scheduling", True)
    monkeypatch.setattr(settings, "automation_enabled", True)
    monkeypatch.setattr(settings, "publish_mode", PublishMode.FACEBOOK_SCHEDULE)
    monkeypatch.setattr(settings, "facebook_page_id", "123456")
    monkeypatch.setattr(settings, "facebook_page_access_token", SecretStr("fixture-page-token"))
    return settings


@pytest.mark.parametrize("allow_live,automation,live_mode", list(product([False, True], repeat=3)))
def test_bridge_live_gate_matrix(mcp_client, monkeypatch, allow_live, automation, live_mode):
    settings = enable_live(monkeypatch)
    monkeypatch.setattr(settings, "mcp_bridge_allow_live_scheduling", allow_live)
    monkeypatch.setattr(settings, "automation_enabled", automation)
    monkeypatch.setattr(settings, "publish_mode", PublishMode.FACEBOOK_SCHEDULE if live_mode else PublishMode.DRY_RUN)
    writes = []

    async def accepted(self, **kwargs):
        writes.append(kwargs)
        return FacebookScheduledPhoto(id="fixture-photo", post_id="fixture-page_post")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", accepted)
    enabled = allow_live and automation and live_mode
    status = call(mcp_client, "get_system_status")["data"]
    assert status["bridge_client_restricted"] is True
    assert status["bridge_live_scheduling_enabled"] is enabled
    assert status["publishing_enabled"] is (automation and live_mode)
    post = call(mcp_client, "create_post", create_args())["data"]
    assert post["status"] == "draft" and writes == []
    result = call(mcp_client, "schedule_post", {"post_id": post["id"], "mode": "facebook_schedule"})
    persisted = call(mcp_client, "get_post", {"post_id": post["id"]})["data"]
    if enabled:
        assert result["ok"] and result["data"]["simulated"] is False
        assert result["data"]["external_request_made"] is True
        assert persisted["status"] == "scheduled"
        assert persisted["facebook_object_id"] == "fixture-page_post"
        assert len(writes) == 1
        assert writes[0]["image_mime_type"] == "image/png"
        assert isinstance(writes[0]["image_content"], bytes)
        again = call(mcp_client, "schedule_post", {"post_id": post["id"], "mode": "facebook_schedule"})
        assert again["error"]["code"] == "INVALID_POST_STATE"
        assert len(writes) == 1
    else:
        assert result["error"]["code"] == "BRIDGE_ACTION_FORBIDDEN"
        assert persisted["status"] == "draft" and persisted["attempts"] == []
        assert writes == []


@pytest.mark.parametrize("configured,caller", [
    (None, "chatgpt-client"), ("", "chatgpt-client"),
    ("dedicated-bridge", "chatgpt-client"), ("chatgpt-client", "another-client"),
])
def test_live_status_is_false_for_every_other_client(mcp_client, signing_key, monkeypatch, configured, caller):
    settings = enable_live(monkeypatch)
    monkeypatch.setattr(settings, "mcp_bridge_client_id", configured)
    mcp_client.headers["Authorization"] = f"Bearer {token(signing_key, client_id=caller)}"
    mcp_client.headers["X-Client-Id"] = "chatgpt-client"
    status = call(mcp_client, "get_system_status")["data"]
    assert status["publishing_enabled"] is True
    assert status["bridge_client_restricted"] is False
    assert status["bridge_live_scheduling_enabled"] is False


def test_live_gate_does_not_accept_forged_tokens(mcp_client, monkeypatch):
    enable_live(monkeypatch)
    mcp_client.headers["Authorization"] = f"Bearer {token(ec.generate_private_key(ec.SECP256R1()))}"
    assert rpc(mcp_client, "tools/call", {"name": "get_system_status"}).status_code == 401
    assert rpc(mcp_client, "tools/call", {"name": "schedule_post", "arguments": {"post_id": "unused", "mode": "facebook_schedule"}}).status_code == 401


@pytest.mark.parametrize("mode", [{}, {"mode": "dry_run"}])
def test_bridge_dry_run_never_publishes_with_every_gate_enabled(mcp_client, monkeypatch, mode):
    enable_live(monkeypatch)
    writes = []

    async def forbidden(self, **kwargs):
        writes.append(True)
        raise AssertionError("Dry run reached Meta")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden)
    post = call(mcp_client, "create_post", create_args())["data"]
    result = call(mcp_client, "schedule_post", {"post_id": post["id"], **mode})
    assert result["ok"] and result["data"]["simulated"] is True
    assert result["data"]["external_request_made"] is False
    assert result["data"]["facebook_object_id"] is None
    assert writes == []


@pytest.mark.parametrize("name,args", [
    ("update_post", {"post_id": "unused", "caption": "blocked"}),
    ("create_and_schedule_post", {**create_args(), "mode": "dry_run"}),
    ("create_and_schedule_post", {**create_args(), "mode": "facebook_schedule"}),
])
def test_other_bridge_denials_remain_with_live_enabled(mcp_client, monkeypatch, name, args):
    enable_live(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden action reached domain logic")

    monkeypatch.setattr(mcp_host.tools, "_execute", forbidden)
    monkeypatch.setattr(mcp_host.tools, "_reserve", forbidden)
    assert call(mcp_client, name, args)["error"]["code"] == "BRIDGE_ACTION_FORBIDDEN"


def test_unknown_outcome_remains_blocked_with_live_enabled(mcp_client, monkeypatch):
    enable_live(monkeypatch)
    writes = []

    async def uncertain(self, **kwargs):
        writes.append(True)
        raise FacebookWriteError(code=FacebookWriteErrorCode.OUTCOME_UNKNOWN, safe_message="Unknown fixture outcome", outcome_unknown=True)

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", uncertain)
    post = call(mcp_client, "create_post", create_args())["data"]
    args = {"post_id": post["id"], "mode": "facebook_schedule"}
    assert call(mcp_client, "schedule_post", args)["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    assert call(mcp_client, "schedule_post", args)["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    assert call(mcp_client, "schedule_post", {"post_id": post["id"], "mode": "dry_run"})["error"]["code"] == "FACEBOOK_OUTCOME_UNKNOWN"
    assert writes == [True]
    assert len(call(mcp_client, "get_post", {"post_id": post["id"]})["data"]["attempts"]) == 1


def test_concurrent_bridge_live_attempts_make_one_mocked_write(mcp_client, monkeypatch):
    enable_live(monkeypatch)
    post = call(mcp_client, "create_post", create_args())["data"]
    entered, release = Event(), Event()
    writes = []

    async def accepted(self, **kwargs):
        import anyio
        writes.append(True)
        entered.set()
        assert await anyio.to_thread.run_sync(lambda: release.wait(10))
        return FacebookScheduledPhoto(id="fixture-photo")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", accepted)
    args = {"post_id": post["id"], "mode": "facebook_schedule"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, mcp_client, "schedule_post", args)
        try:
            assert entered.wait(5)
            second = pool.submit(call, mcp_client, "schedule_post", args).result(timeout=5)
            assert second["error"]["code"] == "DUPLICATE_ATTEMPT_RISK"
        finally:
            release.set()
        assert first.result(timeout=5)["ok"]
    assert writes == [True]


def test_gate_enablement_and_status_do_not_process_existing_posts(mcp_client, monkeypatch):
    async def forbidden(self, **kwargs):
        raise AssertionError("Enabling capability must not process drafts")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden)
    draft_args = create_args()
    draft = call(mcp_client, "create_post", draft_args)["data"]
    ready = call(mcp_client, "create_post", create_args("existing-ready-request"))["data"]
    assert call(mcp_client, "schedule_post", {"post_id": ready["id"]})["data"]["simulated"]
    enable_live(monkeypatch)
    replay = call(mcp_client, "create_post", draft_args)
    assert replay["replayed"] is True and replay["data"]["id"] == draft["id"]
    conflict = call(mcp_client, "create_post", {**draft_args, "caption": "Changed request"})
    assert conflict["error"]["code"] == "REQUEST_KEY_CONFLICT"
    for _ in range(2):
        assert call(mcp_client, "get_system_status")["data"]["bridge_live_scheduling_enabled"] is True
    assert call(mcp_client, "get_post", {"post_id": draft["id"]})["data"]["status"] == "draft"
    persisted = call(mcp_client, "get_post", {"post_id": ready["id"]})["data"]
    assert persisted["status"] == "ready"
    assert len(persisted["attempts"]) == 1
    assert persisted["attempts"][0]["external_request_made"] is False


def test_bridge_live_still_rejects_corrupt_stored_image(mcp_client, fake_media, monkeypatch):
    enable_live(monkeypatch)
    writes = []

    async def forbidden(self, **kwargs):
        writes.append(True)
        raise AssertionError("Invalid image reached Meta")

    monkeypatch.setattr(FacebookClient, "schedule_page_photo", forbidden)
    post = call(mcp_client, "create_post", create_args())["data"]
    object_path = post["image_url"].removeprefix("/api/media/")
    content, mime, _ = corrupt_image_bytes("png-pixels")
    fake_media.objects[object_path] = StoredObject(content=content, mime_type=mime)
    monkeypatch.setattr(fake_media.validator, "get_object", fake_media.get_object)
    monkeypatch.setattr(fake_media, "get_validated_object", fake_media.validator.get_validated_object)
    result = call(mcp_client, "schedule_post", {"post_id": post["id"], "mode": "facebook_schedule"})
    assert result["error"]["code"] == "INVALID_STORED_IMAGE"
    persisted = call(mcp_client, "get_post", {"post_id": post["id"]})["data"]
    assert persisted["attempts"][0]["external_request_made"] is False
    assert writes == []


def test_new_gate_defaults_off_and_rejects_invalid_configuration(monkeypatch):
    assert Settings(_env_file=None).mcp_bridge_allow_live_scheduling is False
    with monkeypatch.context() as environment:
        environment.setenv("MCP_BRIDGE_ALLOW_LIVE_SCHEDULING", "true")
        assert Settings(_env_file=None).mcp_bridge_allow_live_scheduling is True
        environment.setenv("MCP_BRIDGE_ALLOW_LIVE_SCHEDULING", "invalid")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
