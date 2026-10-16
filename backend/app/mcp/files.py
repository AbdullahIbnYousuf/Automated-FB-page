"""Bounded downloads of temporary ChatGPT file inputs, without credential forwarding."""

import ipaddress
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

    async def _validate_url(self, value: str) -> None:
        try:
            url = urlsplit(value)
            host = (url.hostname or "").lower()
            allowed = {h.strip().lower() for h in self.settings.mcp_file_allowed_hosts.split(",") if h.strip()}
            if url.scheme != "https" or url.username is not None or url.password is not None or url.fragment:
                raise ValueError()
            if url.port not in {None, 443} or host not in allowed or "*" in host:
                raise ValueError()
            # Even an explicitly configured host must never resolve to a private destination.
            addresses = await anyio.to_thread.run_sync(
                lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            )
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise ValueError()
        except (ValueError, OSError) as exc:
            raise AppError(
                code="FILE_URL_NOT_ALLOWED", status_code=422,
                message="The image URL must use a verified ChatGPT HTTPS file host. Reattach the image or use the dashboard.",
            ) from exc

    async def download(self, file: ChatGPTFile) -> UploadFile:
        current_url = file.download_url
        try:
            with anyio.fail_after(self.settings.mcp_file_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.mcp_file_timeout_seconds,
                    follow_redirects=False, trust_env=False, transport=self.transport,
                    headers={"Accept": "image/jpeg,image/png", "Accept-Encoding": "identity"},
                ) as client:
                    for _ in range(3):
                        await self._validate_url(current_url)
                        async with client.stream("GET", current_url) as response:
                            if response.is_redirect:
                                destination = response.headers.get("location")
                                if not destination:
                                    break
                                current_url = urljoin(current_url, destination)
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
