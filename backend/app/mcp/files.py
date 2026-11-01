"""Bounded downloads of temporary ChatGPT file inputs, without credential forwarding."""

import ipaddress
import logging
import re
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import anyio
import httpx
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers

from app.config import Settings
from app.services.errors import AppError


logger = logging.getLogger(__name__)


def diagnostic_hostname(host: str | None) -> str | None:
    """Return only a bounded hostname, never malformed authority/path text."""
    if not host or len(host) > 253 or "%" in host:
        return None
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        pass
    try:
        normalized = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    return normalized if re.fullmatch(r"[a-z0-9.-]{1,253}", normalized) else None


class ChatGPTFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    download_url: str = Field(min_length=1, max_length=8192)
    file_id: str = Field(min_length=1, max_length=256)
    mime_type: str = Field(default="", max_length=128)
    file_name: str = Field(default="", max_length=255)


class ChatGPTFileDownloader:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def _url_rejected(self, category: str, host: str | None, hop: int) -> AppError:
        # Never include the URL, exception, file ID or request metadata here.
        logger.warning(
            "ChatGPT file URL rejected",
            extra={
                "event": "mcp_file_url_rejected",
                "rejection_category": category,
                "hostname": diagnostic_hostname(host),
                "redirect_hop": hop,
            },
        )
        return AppError(
            code="FILE_URL_NOT_ALLOWED", status_code=422,
            message="The image URL must use a verified ChatGPT HTTPS file host. Reattach the image or use the dashboard.",
        )

    async def _validate_url(self, value: str, *, redirect_hop: int = 0) -> None:
        host = None
        try:
            url = urlsplit(value)
            host = (url.hostname or "").lower()
            port = url.port
        except ValueError:
            raise self._url_rejected("url_parse_error", host, redirect_hop) from None
        if url.scheme != "https":
            raise self._url_rejected("scheme_not_https", host, redirect_hop)
        if url.username is not None or url.password is not None:
            raise self._url_rejected("userinfo_not_allowed", host, redirect_hop)
        if url.fragment:
            raise self._url_rejected("fragment_not_allowed", host, redirect_hop)
        if port not in {None, 443}:
            raise self._url_rejected("port_not_allowed", host, redirect_hop)
        allowed = {h.strip().lower() for h in self.settings.mcp_file_allowed_hosts.split(",") if h.strip()}
        if not host or host not in allowed or "*" in host:
            raise self._url_rejected("host_not_allowed", host, redirect_hop)
        # Even an explicitly configured host must never resolve to a private destination.
        try:
            addresses = await anyio.to_thread.run_sync(
                lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            )
        except OSError:
            raise self._url_rejected("dns_lookup_failed", host, redirect_hop) from None
        if not addresses:
            raise self._url_rejected("dns_no_addresses", host, redirect_hop)
        try:
            public = all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
        except ValueError:
            raise self._url_rejected("dns_invalid_address", host, redirect_hop) from None
        if not public:
            raise self._url_rejected("dns_non_public", host, redirect_hop)

    async def download(self, file: ChatGPTFile) -> UploadFile:
        current_url = file.download_url
        try:
            with anyio.fail_after(self.settings.mcp_file_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.mcp_file_timeout_seconds,
                    follow_redirects=False, trust_env=False, transport=self.transport,
                    headers={"Accept": "image/jpeg,image/png", "Accept-Encoding": "identity"},
                ) as client:
                    for hop in range(3):
                        await self._validate_url(current_url, redirect_hop=hop)
                        async with client.stream("GET", current_url) as response:
                            if response.is_redirect:
                                destination = response.headers.get("location")
                                if not destination:
                                    break
                                try:
                                    current_url = urljoin(current_url, destination)
                                except ValueError:
                                    raise self._url_rejected("url_parse_error", None, hop + 1) from None
                                continue
                            if response.status_code != 200:
                                raise AppError(
                                    code="FILE_UNAVAILABLE", status_code=422,
                                    message="The ChatGPT image could not be downloaded. Its link may have expired; reattach it.",
                                )
                            size = response.headers.get("content-length")
                            if size and (not size.isdigit() or int(size) > self.settings.max_upload_bytes):
                                raise self._too_large()
                            if response.headers.get("content-encoding", "identity").lower() != "identity":
                                raise AppError(code="INVALID_IMAGE", message="Encoded file responses are not supported.", status_code=422)
                            content = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                content.extend(chunk)
                                if len(content) > self.settings.max_upload_bytes:
                                    raise self._too_large()
                            return self._upload(bytes(content), file)
        except (httpx.HTTPError, TimeoutError) as exc:
            raise AppError(
                code="FILE_UNAVAILABLE", status_code=422,
                message="The ChatGPT image download failed. Reattach the image; no Facebook request was made.",
            ) from exc
        raise AppError(code="FILE_UNAVAILABLE", message="The image redirected too many times. Reattach it.", status_code=422)

    def _upload(self, content: bytes, file: ChatGPTFile) -> UploadFile:
        try:
            with Image.open(BytesIO(content)) as image:
                kind = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png")}.get(image.format or "")
                if kind is None:
                    raise ValueError()
        except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise AppError(code="INVALID_IMAGE", message="Attach one valid JPEG or PNG image.", status_code=422) from exc
        mime, extension = kind
        name = Path(file.file_name.replace("\\", "/")).name if file.file_name else f"chatgpt-image{extension}"
        if file.mime_type and file.mime_type != mime:
            raise AppError(code="UNSUPPORTED_IMAGE", message="The supplied image type does not match its content.", status_code=422)
        # MediaService performs extension, MIME, decoded-content, dimensions and size validation.
        return UploadFile(file=BytesIO(content), filename=name, headers=Headers({"content-type": mime}))

    @staticmethod
    def _too_large() -> AppError:
        return AppError(code="IMAGE_TOO_LARGE", message="The image exceeds the configured upload limit.", status_code=413)
