"""Downloader rejection categories, redaction and outbound-request safeguards."""

import json
import socket

import anyio
import httpx
import pytest

from app.config import get_settings
from app.logging_config import JsonFormatter
from app.mcp.files import ChatGPTFile, ChatGPTFileDownloader, diagnostic_hostname
from app.services.errors import AppError
from tests.helpers import image_bytes


HOST = "files.oaiusercontent.com"
PRIVATE_PATH = "/private-file-path-canary"
PRIVATE_QUERY = "?sig=signed-query-canary"


def addresses(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


def rejection(caplog):
    records = [r for r in caplog.records if getattr(r, "event", None) == "mcp_file_url_rejected"]
    assert len(records) == 1
    record = records[0]
    payload = json.loads(JsonFormatter().format(record))
    assert set(payload) == {
        "timestamp", "level", "logger", "message", "event",
        "rejection_category", "hostname", "redirect_hop",
    }
    assert record.exc_info is None and record.args == ()
    # Check both the emitted JSON and raw record: no secrets hidden in extras.
    serialized = json.dumps(record.__dict__, default=str) + json.dumps(payload)
    for forbidden in [PRIVATE_PATH, "signed-query-canary", "userinfo-canary", "password-canary", "https://", "Authorization", "Bearer"]:
        assert forbidden not in serialized
    return payload


@pytest.mark.parametrize("base,category,host", [
    ("http://files.oaiusercontent.com", "scheme_not_https", HOST),
    ("sandbox:", "scheme_not_https", None),
    ("https://userinfo-canary:password-canary@files.oaiusercontent.com", "userinfo_not_allowed", HOST),
    ("https://files.oaiusercontent.com:8443", "port_not_allowed", HOST),
    ("https://files.oaiusercontent.com:bad", "url_parse_error", HOST),
    ("https://files.oaiusercontent.com:65536", "url_parse_error", HOST),
    ("https://[invalid-authority", "url_parse_error", None),
    ("https:///", "host_not_allowed", None),
    ("https://files.oaiusercontent.com.evil.example", "host_not_allowed", "files.oaiusercontent.com.evil.example"),
    ("https://other.oaiusercontent.com", "host_not_allowed", "other.oaiusercontent.com"),
    ("https://files.oaiusercontent.com.", "host_not_allowed", "files.oaiusercontent.com."),
    ("https://files.oaiusercontent.com\\userinfo-canary", "host_not_allowed", None),
    ("https://files.oaiusercontent.com%2fuserinfo-canary", "host_not_allowed", None),
    ("https://*.oaiusercontent.com", "host_not_allowed", None),
    ("https://127.0.0.1", "host_not_allowed", "127.0.0.1"),
    ("https://[::1]", "host_not_allowed", "::1"),
])
def test_url_policy_rejects_before_dns_or_http_and_logs_only_safe_fields(
    monkeypatch, caplog, base, category, host,
):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: pytest.fail("Rejected URL reached DNS"))
    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(lambda r: pytest.fail("Rejected URL reached HTTP")))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url=base + PRIVATE_PATH + PRIVATE_QUERY, file_id="fixture-file"))
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    payload = rejection(caplog)
    assert (payload["rejection_category"], payload["hostname"], payload["redirect_hop"]) == (category, host, 0)


@pytest.mark.parametrize("dns_result,category", [
    (socket.gaierror("resolver-private-details"), "dns_lookup_failed"),
    ([], "dns_no_addresses"),
    (addresses("invalid-address"), "dns_invalid_address"),
    (addresses("10.0.0.1"), "dns_non_public"),
    (addresses("127.0.0.1"), "dns_non_public"),
    (addresses("169.254.169.254"), "dns_non_public"),
    (addresses("::1"), "dns_non_public"),
    (addresses("fc00::1"), "dns_non_public"),
    (addresses("8.8.8.8", "10.0.0.1"), "dns_non_public"),
])
def test_allowlisted_host_dns_rejection_is_distinct_and_never_connects(monkeypatch, caplog, dns_result, category):
    def resolve(*args, **kwargs):
        if isinstance(dns_result, OSError):
            raise dns_result
        return dns_result

    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", resolve)
    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(lambda r: pytest.fail("Unsafe DNS reached HTTP")))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{HOST}" + PRIVATE_PATH + PRIVATE_QUERY, file_id="fixture-file"))
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    payload = rejection(caplog)
    assert payload["rejection_category"] == category
    assert payload["hostname"] == HOST and payload["redirect_hop"] == 0
    assert "resolver-private-details" not in json.dumps(payload)


def test_fragment_rejection_does_not_record_fragment(monkeypatch, caplog):
    downloader = ChatGPTFileDownloader(get_settings())
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{HOST}" + PRIVATE_PATH + PRIVATE_QUERY + "#fragment-canary", file_id="fixture-file"))
    payload = rejection(caplog)
    assert payload["rejection_category"] == "fragment_not_allowed"
    assert "fragment-canary" not in json.dumps(payload)


@pytest.mark.parametrize("destination,category,host", [
    ("https://unverified.example" + PRIVATE_PATH + PRIVATE_QUERY, "host_not_allowed", "unverified.example"),
    ("http://files.oaiusercontent.com" + PRIVATE_PATH + PRIVATE_QUERY, "scheme_not_https", HOST),
    ("https://files.oaiusercontent.com:8443" + PRIVATE_PATH + PRIVATE_QUERY, "port_not_allowed", HOST),
    ("https://[invalid-authority", "url_parse_error", None),
])
def test_redirect_destination_is_revalidated_and_logs_its_hop(monkeypatch, caplog, destination, category, host):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    requests = []

    def redirect(request):
        requests.append(request.method)
        return httpx.Response(302, headers={"location": destination})

    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{HOST}/first", file_id="fixture-file"))
    assert error.value.code == "FILE_URL_NOT_ALLOWED"
    assert requests == ["GET"]
    payload = rejection(caplog)
    assert (payload["rejection_category"], payload["hostname"], payload["redirect_hop"]) == (category, host, 1)


def test_same_host_redirect_checks_dns_again(monkeypatch, caplog):
    resolutions = iter([addresses("8.8.8.8"), addresses("10.0.0.1")])
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: next(resolutions))
    requests = []

    def redirect(request):
        requests.append(request.method)
        return httpx.Response(302, headers={"location": PRIVATE_PATH + PRIVATE_QUERY})

    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError):
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{HOST}/first", file_id="fixture-file"))
    assert requests == ["GET"]
    payload = rejection(caplog)
    assert payload["rejection_category"] == "dns_non_public"
    assert payload["redirect_hop"] == 1


def test_public_allowed_download_and_relative_redirect_keep_credentials_out(monkeypatch, caplog):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8", "2001:4860:4860::8888"))
    requests = []

    def handle(request):
        requests.append(request.method)
        assert request.url.host == HOST
        assert not any(header in request.headers for header in ("authorization", "apikey", "cookie"))
        if len(requests) == 1:
            return httpx.Response(302, headers={"location": PRIVATE_PATH + PRIVATE_QUERY})
        return httpx.Response(200, content=image_bytes(), headers={"content-type": "image/png"})

    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(handle))
    upload = anyio.run(downloader.download, ChatGPTFile(download_url=f"https://FILES.OAIUSERCONTENT.COM:443/first", file_id="fixture-file"))
    assert requests == ["GET", "GET"]
    assert anyio.run(upload.read) == image_bytes()
    assert not [r for r in caplog.records if getattr(r, "event", None) == "mcp_file_url_rejected"]


def test_redirect_loop_is_bounded(monkeypatch):
    monkeypatch.setattr("app.mcp.files.socket.getaddrinfo", lambda *a, **kw: addresses("8.8.8.8"))
    requests = []

    def redirect(request):
        requests.append(request.method)
        return httpx.Response(302, headers={"location": "/loop"})

    downloader = ChatGPTFileDownloader(get_settings(), transport=httpx.MockTransport(redirect))
    with pytest.raises(AppError) as error:
        anyio.run(downloader.download, ChatGPTFile(download_url=f"https://{HOST}/first", file_id="fixture-file"))
    assert error.value.code == "FILE_UNAVAILABLE"
    assert requests == ["GET"] * 3


@pytest.mark.parametrize("host,expected", [
    ("FILES.OAIUSERCONTENT.COM", HOST),
    ("bücher.example", "xn--bcher-kva.example"),
    ("2001:4860:4860:0:0:0:0:8888", "2001:4860:4860::8888"),
    (None, None), ("", None), ("x" * 254, None),
    ("host/path-canary", None), ("host?query-canary", None),
    ("host\\path-canary", None), ("host\ncontrol-canary", None),
    ("host%0aquery-canary", None), ("host@userinfo-canary", None),
])
def test_diagnostic_hostname_cannot_include_other_url_parts(host, expected):
    assert diagnostic_hostname(host) == expected
