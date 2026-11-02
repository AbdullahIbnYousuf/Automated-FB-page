"""Observed generated-image delivery host, using isolated HTTP/storage/Meta."""

import anyio
import httpx
import pytest

from app.config import PublishMode, get_settings
from app.main import mcp_host
from app.mcp.files import ChatGPTFile, ChatGPTFileDownloader
from app.services.errors import AppError
from tests.test_mcp import call, create_args, mcp_client, png, signing_key
from tests.test_mcp_files import addresses


GENERATED_HOST = "oaisdmntprcentralindia.blob.core.windows.net"
GENERATED_ALIAS = "sdmntprindiasocentral.oaiusercontent.com"
GENERATED_HOSTS = (GENERATED_HOST, GENERATED_ALIAS, "sdmntprcentralindia.oaiusercontent.com")
PREVIOUS_HOSTS = "files.oaiusercontent.com,sdmntprnznorth.oaiusercontent.com,oaisdmntprnznorth.blob.core.windows.net"
VERIFIED_HOSTS = ",".join((PREVIOUS_HOSTS, *GENERATED_HOSTS))


@pytest.mark.parametrize("host", GENERATED_HOSTS)
def test_observed_host_needs_explicit_configuration(monkeypatch, caplog, host):
    settings = get_settings().model_copy(update={"mcp_file_allowed_hosts": PREVIOUS_HOSTS})
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Rejected host reached DNS"))
    downloader = ChatGPTFileDownloader(settings)
    with pytest.raises(AppError) as error:
        anyio.run(downloader._validate_url, f"https://{host}/fixture?sig=canary")
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    record = next(r for r in caplog.records if getattr(r, "event", None) == "mcp_file_url_rejected")
    assert (record.rejection_category, record.hostname, record.redirect_hop) == ("host_not_allowed", host, 0)


@pytest.mark.parametrize("url", [
    f"https://{GENERATED_HOST}.evil.example/fixture",
    f"https://child.{GENERATED_HOST}/fixture",
    "https://other.blob.core.windows.net/fixture",
    "https://*.blob.core.windows.net/fixture",
    f"https://{GENERATED_HOST}./fixture",
    f"https://{GENERATED_HOST}%2f.evil.example/fixture",
    f"https://{GENERATED_HOST}:bad/fixture",
    f"https://{GENERATED_HOST}:8443/fixture",
    f"https://{GENERATED_HOST}@evil.example/fixture",
    f"http://{GENERATED_HOST}/fixture",
    f"https://{GENERATED_HOST}/fixture#fragment",
    f"https://{GENERATED_ALIAS}.evil.example/fixture",
    f"https://child.{GENERATED_ALIAS}/fixture",
    "https://other.oaiusercontent.com/fixture",
])
def test_generated_host_configuration_still_rejects_hostile_urls(monkeypatch, url):
    settings = get_settings().model_copy(update={"mcp_file_allowed_hosts": VERIFIED_HOSTS})
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Hostile URL reached DNS"))
    with pytest.raises(AppError) as error:
        anyio.run(ChatGPTFileDownloader(settings)._validate_url, url)
    assert error.value.code == "FILE_URL_NOT_ALLOWED"


@pytest.mark.parametrize("ips", [("10.0.0.1",), ("8.8.8.8", "127.0.0.1")])
def test_generated_host_must_still_resolve_only_to_public_addresses(monkeypatch, ips):
    settings = get_settings().model_copy(update={"mcp_file_allowed_hosts": VERIFIED_HOSTS})
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses(*ips))
    with pytest.raises(AppError) as error:
        anyio.run(ChatGPTFileDownloader(settings)._validate_url, f"https://{GENERATED_HOST}/fixture")
    assert error.value.code == "FILE_URL_NOT_ALLOWED"


def test_generated_host_redirect_to_unverified_storage_is_blocked(monkeypatch, caplog):
    settings = get_settings().model_copy(update={"mcp_file_allowed_hosts": VERIFIED_HOSTS})
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    seen = []

    def redirect(request):
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://other.blob.core.windows.net/fixture?sig=canary"})

    downloader = ChatGPTFileDownloader(settings, transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{GENERATED_HOST}/fixture", file_id="fixture"))
    assert seen == [GENERATED_HOST]
    record = next(r for r in caplog.records if getattr(r, "event", None) == "mcp_file_url_rejected")
    assert (record.rejection_category, record.hostname, record.redirect_hop) == ("host_not_allowed", "other.blob.core.windows.net", 1)


@pytest.mark.parametrize("corrupt", [False, True])
@pytest.mark.parametrize("host", GENERATED_HOSTS)
def test_generated_file_download_storage_retrieval_replay_and_dry_run(
    mcp_client, fake_media, monkeypatch, corrupt, host,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_file_allowed_hosts", VERIFIED_HOSTS)
    monkeypatch.setattr(settings, "mcp_bridge_client_id", "chatgpt-client")
    monkeypatch.setattr(settings, "mcp_bridge_allow_live_scheduling", True)
    monkeypatch.setattr(settings, "automation_enabled", True)
    monkeypatch.setattr(settings, "publish_mode", PublishMode.FACEBOOK_SCHEDULE)
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    original = png()
    delivered = original[:-12] if corrupt else original
    requests = []

    def handle(request):
        requests.append(request.url.host)
        assert request.method == "GET"
        assert not any(h in request.headers for h in ("authorization", "apikey", "cookie"))
        return httpx.Response(200, content=delivered, headers={"content-type": "image/png"})

    async def never_publish(*args, **kwargs):
        pytest.fail("Draft or explicit dry run attempted Meta publishing")

    monkeypatch.setattr("app.integrations.facebook.client.FacebookClient.schedule_page_photo", never_publish)
    # Use the production downloader and image validator, not the fixture's shortcut.
    monkeypatch.setattr(mcp_host.tools, "downloader", ChatGPTFileDownloader(settings, transport=httpx.MockTransport(handle)))
    args = create_args("generated-image-transfer-001")
    args["image"] = {"download_url": f"https://{host}/fixture?sig=canary", "file_id": "file_generated_fixture", "file_name": "generated.png", "mime_type": "image/png"}
    result = call(mcp_client, "create_post", args)
    if corrupt:
        assert not result["ok"]
        assert result["error"]["code"] == "INVALID_IMAGE"
        assert fake_media.objects == {}
        assert call(mcp_client, "list_posts")["data"]["total"] == 0
    else:
        assert result["ok"] and result["data"]["status"] == "draft"
        assert len(fake_media.objects) == 1
        assert next(iter(fake_media.objects.values())).content == original
        post_id = result["data"]["id"]
        assert call(mcp_client, "get_post", {"post_id": post_id})["data"]["image_mime_type"] == "image/png"
        dry_run = call(mcp_client, "schedule_post", {"post_id": post_id, "mode": "dry_run"})["data"]
        assert dry_run["simulated"] is True
        assert dry_run["external_request_made"] is False
        assert dry_run["facebook_object_id"] is None
    refreshed = {**args, "image": {**args["image"], "download_url": f"https://{host}/renewed?sig=changed"}}
    replay = call(mcp_client, "create_post", refreshed)
    assert replay["replayed"] and replay["ok"] == result["ok"]
    assert requests == [host]
