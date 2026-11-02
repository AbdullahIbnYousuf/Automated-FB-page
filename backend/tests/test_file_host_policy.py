"""Reviewed first-party suffix policy and unchanged exact-host/DNS boundaries."""

import anyio
import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import mcp_host
from app.mcp.files import ChatGPTFile, ChatGPTFileDownloader
from app.services.errors import AppError
from tests.test_generated_image_transfer import VERIFIED_HOSTS
from tests.test_mcp import call, create_args, mcp_client, png, signing_key
from tests.test_mcp_files import PRIVATE_PATH, PRIVATE_QUERY, addresses, rejection


REGIONAL = "sdmntprseasia.oaiusercontent.com"
AZURE = "oaisdmntprindiasocentral.blob.core.windows.net"


def policy(**overrides):
    return get_settings().model_copy(update={"mcp_file_allowed_domain_suffixes": "oaiusercontent.com", **overrides})


def test_suffix_setting_defaults_empty_and_loads_normalized_environment(monkeypatch):
    assert Settings(_env_file=None).mcp_file_allowed_domain_suffixes == ""
    monkeypatch.setenv("MCP_FILE_ALLOWED_DOMAIN_SUFFIXES", " OAIUSERCONTENT.COM, oaiusercontent.com ")
    assert Settings(_env_file=None).mcp_file_allowed_domain_suffixes == "oaiusercontent.com"


@pytest.mark.parametrize("value", [
    "com", "windows.net", "blob.core.windows.net", "amazonaws.com",
    "*.oaiusercontent.com", ".oaiusercontent.com", "files.oaiusercontent.com",
    "oaiusercontent.com.evil.example", "eviloaiusercontent.com",
    "oaiusercontent.com,blob.core.windows.net", "oaiusercontent.com,com",
    "https://oaiusercontent.com", "oaiusercontent.com.",
])
def test_unsupported_suffix_configuration_fails_closed(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_file_allowed_domain_suffixes=value)


def test_unsupported_environment_suffix_is_rejected(monkeypatch):
    with monkeypatch.context() as environment:
        environment.setenv("MCP_FILE_ALLOWED_DOMAIN_SUFFIXES", "blob.core.windows.net")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


@pytest.mark.parametrize("host", [
    REGIONAL, "sdmntprcentralindia.oaiusercontent.com",
    "sdmntprindiasocentral.oaiusercontent.com", "a.b.oaiusercontent.com",
    "r-2.oaiusercontent.com", "SDMNTPRSEASIA.OAIUSERCONTENT.COM",
])
def test_valid_regional_download_checks_dns_and_never_sends_credentials(monkeypatch, host):
    resolved, fetched = [], []

    def resolve(name, *args, **kwargs):
        resolved.append(name)
        return addresses("8.8.8.8", "2001:4860:4860::8888")

    def download(request):
        fetched.append(request.url.host)
        assert request.method == "GET"
        assert not any(h in request.headers for h in ("authorization", "cookie", "apikey"))
        return httpx.Response(200, content=png())

    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", resolve)
    downloader = ChatGPTFileDownloader(policy(), transport=httpx.MockTransport(download))
    upload = anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{host}:443/fixture", file_id="fixture"))
    assert anyio.run(upload.read) == png()
    anyio.run(upload.close)
    assert resolved == fetched == [host.lower()]


@pytest.mark.parametrize("suffix", ["", "oaiusercontent.com"])
@pytest.mark.parametrize("host", [*VERIFIED_HOSTS.split(","), AZURE])
def test_existing_exact_hosts_remain_compatible(monkeypatch, suffix, host):
    settings = policy(mcp_file_allowed_hosts=f" {VERIFIED_HOSTS},{AZURE.upper()} ", mcp_file_allowed_domain_suffixes=suffix)
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    anyio.run(ChatGPTFileDownloader(settings)._validate_url, f"https://{host}/fixture")


@pytest.mark.parametrize("host", [
    "eviloaiusercontent.com", "oaiusercontent.com.evil.example",
    "files.oaiusercontent.com.evil.example", "oaiusercontent.com",
    AZURE, "other.blob.core.windows.net", "sub.files.example",
])
def test_suffix_never_grants_apex_lookalikes_or_azure(monkeypatch, caplog, host):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Disallowed host reached DNS"))
    with pytest.raises(AppError) as error:
        anyio.run(ChatGPTFileDownloader(policy())._validate_url, f"https://{host}" + PRIVATE_PATH + PRIVATE_QUERY)
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    assert rejection(caplog)["rejection_category"] == "host_not_allowed"


def test_disabled_suffix_does_not_expand_exact_host_matching(monkeypatch):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Disabled suffix reached DNS"))
    with pytest.raises(AppError):
        anyio.run(ChatGPTFileDownloader(get_settings())._validate_url, f"https://{REGIONAL}/fixture")


@pytest.mark.parametrize("host", [
    ".oaiusercontent.com", "a..oaiusercontent.com", "-a.oaiusercontent.com",
    "a-.oaiusercontent.com", "a_b.oaiusercontent.com", "a.oaiusercontent.com.",
    "a" * 64 + ".oaiusercontent.com",
    ".".join(["a" * 60] * 4) + ".oaiusercontent.com",
    "*.oaiusercontent.com", "a%2eoaiusercontent.com", "a%00.oaiusercontent.com",
    "a\\.oaiusercontent.com", "é.oaiusercontent.com", "K.oaiusercontent.com",
    "a。oaiusercontent.com", "a\u200d.oaiusercontent.com",
])
def test_malformed_hostnames_rejected_even_if_exactly_configured(monkeypatch, caplog, host):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Malformed hostname reached DNS"))
    with pytest.raises(AppError) as error:
        anyio.run(ChatGPTFileDownloader(policy(mcp_file_allowed_hosts=host))._validate_url, f"https://{host}" + PRIVATE_PATH + PRIVATE_QUERY)
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    assert rejection(caplog)["rejection_category"] == "host_not_allowed"


@pytest.mark.parametrize("value", [
    f" https://{REGIONAL}/fixture", f"https://sdmntpr\nseasia.oaiusercontent.com/fixture",
    f"https://{REGIONAL}/fixture?sig=canary\tsecret", f"https://{REGIONAL}/fixture\x7f",
])
def test_url_parser_cannot_remove_raw_controls_or_whitespace(monkeypatch, caplog, value):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Malformed URL reached DNS"))
    with pytest.raises(AppError):
        anyio.run(ChatGPTFileDownloader(policy())._validate_url, value)
    payload = rejection(caplog)
    assert payload["rejection_category"] == "url_parse_error" and payload["hostname"] is None


@pytest.mark.parametrize("value,category", [
    (f"http://{REGIONAL}/fixture", "scheme_not_https"),
    (f"https://userinfo-canary:password-canary@{REGIONAL}/fixture", "userinfo_not_allowed"),
    (f"https://{REGIONAL}:8443/fixture", "port_not_allowed"),
    (f"https://{REGIONAL}:bad/fixture", "url_parse_error"),
    (f"https://{REGIONAL}/fixture#fragment", "fragment_not_allowed"),
])
def test_suffix_does_not_bypass_url_policy(monkeypatch, caplog, value, category):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Unsafe URL reached DNS"))
    with pytest.raises(AppError):
        anyio.run(ChatGPTFileDownloader(policy())._validate_url, value)
    assert rejection(caplog)["rejection_category"] == category


@pytest.mark.parametrize("ips", [("127.0.0.1",), ("169.254.169.254",), ("::1",), ("8.8.8.8", "10.0.0.1")])
def test_suffix_hosts_still_require_all_dns_answers_public(monkeypatch, caplog, ips):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses(*ips))
    downloader = ChatGPTFileDownloader(policy(), transport=httpx.MockTransport(lambda r: pytest.fail("Unsafe DNS reached HTTP")))
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{REGIONAL}" + PRIVATE_PATH + PRIVATE_QUERY, file_id="fixture"))
    assert rejection(caplog)["rejection_category"] == "dns_non_public"


@pytest.mark.parametrize("destination,category", [
    ("https://oaiusercontent.com.evil.example/fixture", "host_not_allowed"),
    (f"https://{AZURE}/fixture", "host_not_allowed"),
    ("https://other.blob.core.windows.net/fixture", "host_not_allowed"),
    (f"http://{REGIONAL}/fixture", "scheme_not_https"),
    ("https://a..oaiusercontent.com/fixture", "host_not_allowed"),
])
def test_regional_redirect_destinations_are_revalidated(monkeypatch, caplog, destination, category):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    requests = []

    def redirect(request):
        requests.append(request.url.host)
        return httpx.Response(302, headers={"location": destination + PRIVATE_QUERY})

    downloader = ChatGPTFileDownloader(policy(), transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{REGIONAL}/fixture", file_id="fixture"))
    assert requests == [REGIONAL]
    payload = rejection(caplog)
    assert (payload["rejection_category"], payload["redirect_hop"]) == (category, 1)


def test_allowed_redirect_target_has_its_dns_rechecked(monkeypatch, caplog):
    answers = iter([addresses("8.8.8.8"), addresses("8.8.8.8", "10.0.0.1")])
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: next(answers))
    requests = []

    def redirect(request):
        requests.append(request.url.host)
        return httpx.Response(302, headers={"location": "https://another.oaiusercontent.com/fixture"})

    downloader = ChatGPTFileDownloader(policy(), transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{REGIONAL}/fixture", file_id="fixture"))
    assert requests == [REGIONAL]
    payload = rejection(caplog)
    assert (payload["rejection_category"], payload["redirect_hop"]) == ("dns_non_public", 1)


@pytest.mark.parametrize("destination", ["another.oaiusercontent.com", AZURE])
def test_regional_redirect_can_reach_reviewed_suffix_or_explicit_account(monkeypatch, destination):
    resolved, requests = [], []

    def resolve(host, *args, **kwargs):
        resolved.append(host)
        return addresses("8.8.8.8")

    def download(request):
        requests.append(request.url.host)
        assert not any(h in request.headers for h in ("authorization", "cookie", "apikey"))
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": f"https://{destination}/fixture"})
        return httpx.Response(200, content=png())

    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", resolve)
    downloader = ChatGPTFileDownloader(policy(mcp_file_allowed_hosts=AZURE), transport=httpx.MockTransport(download))
    upload = anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{REGIONAL}/fixture", file_id="fixture"))
    assert anyio.run(upload.read) == png()
    anyio.run(upload.close)
    assert resolved == requests == [REGIONAL, destination]


def test_unsupported_suffix_cannot_broaden_runtime_policy_if_validation_bypassed(monkeypatch):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Unsupported suffix reached DNS"))
    with pytest.raises(AppError):
        anyio.run(ChatGPTFileDownloader(policy(mcp_file_allowed_domain_suffixes="blob.core.windows.net"))._validate_url, f"https://{AZURE}/fixture")


@pytest.mark.parametrize("corrupt", [False, True])
def test_regional_creation_validates_private_bytes_and_replays_without_redownload(mcp_client, fake_media, monkeypatch, corrupt):
    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_file_allowed_domain_suffixes", "oaiusercontent.com")
    monkeypatch.setattr(settings, "mcp_bridge_client_id", "chatgpt-client")
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    requests = []

    def download(request):
        requests.append(request.url.host)
        return httpx.Response(200, content=png()[:-12] if corrupt else png())

    monkeypatch.setattr(mcp_host.tools, "downloader", ChatGPTFileDownloader(settings, transport=httpx.MockTransport(download)))
    args = create_args("regional-suffix-creation-001")
    args["image"]["download_url"] = f"https://{REGIONAL}/fixture?sig=canary"
    result = call(mcp_client, "create_post", args)
    assert result["ok"] is not corrupt
    if corrupt:
        assert result["error"]["code"] == "INVALID_IMAGE" and not fake_media.objects
        assert call(mcp_client, "list_posts")["data"]["total"] == 0
    else:
        assert result["data"]["status"] == "draft"
        assert next(iter(fake_media.objects.values())).content == png()
    assert call(mcp_client, "create_post", args)["replayed"]
    assert requests == [REGIONAL]
