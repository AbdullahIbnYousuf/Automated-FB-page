"""Validated post media backed by private Supabase Storage buckets."""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import anyio
import httpx
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.services.errors import AppError
from app.services.video_validation import VIDEO_MIME_TYPE, validate_video, video_too_large


ALLOWED_IMAGES = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
}
OBJECT_PATH_PATTERN = re.compile(
    r"^posts/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.(?:jpg|jpeg|png|mp4)$"
)


@dataclass(frozen=True)
class StoredMedia:
    object_path: str
    mime_type: str
    original_filename: str


StoredImage = StoredMedia  # Existing image interfaces and test helpers.


@dataclass(frozen=True)
class StoredObject:
    content: bytes
    mime_type: str


class MediaService:
    """Keep privileged Storage credentials and object operations backend-only."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def store_upload(self, upload: UploadFile) -> StoredImage:
        content, extension, mime_type, display_name = await self._validate_upload(upload)
        object_path = f"posts/{uuid4()}{extension}"
        response = await self._request(
            "PUT",
            self._object_url(object_path),
            headers={"Content-Type": mime_type, "x-upsert": "false"},
            content=content,
        )
        if response.status_code == 409:
            raise AppError(
                code="IMAGE_STORAGE_CONFLICT",
                message="The image could not be stored safely. Try again.",
                status_code=409,
            )
        if response.is_error:
            raise AppError(
                code="IMAGE_STORAGE_ERROR",
                message="The image could not be stored. Try again.",
                status_code=503,
            )
        return StoredImage(
            object_path=object_path,
            mime_type=mime_type,
            original_filename=display_name or f"upload{extension}",
        )

    async def store_video_upload(self, upload: UploadFile) -> StoredMedia:
        filename = Path((upload.filename or "").replace("\\", "/")).name
        if Path(filename).suffix.lower() != ".mp4" or upload.content_type not in {
            VIDEO_MIME_TYPE, "application/octet-stream", None,
        }:
            raise AppError(code="UNSUPPORTED_VIDEO", message="Choose one MP4 video.", status_code=422)
        limit = self.settings.max_video_upload_bytes
        content = await upload.read(limit + 1)
        if len(content) > limit:
            raise video_too_large(limit)
        await anyio.to_thread.run_sync(validate_video, content)
        object_path = f"posts/{uuid4()}.mp4"
        try:
            with anyio.fail_after(self.settings.supabase_request_timeout_seconds):
                response = await self._request(
                    "POST", self._object_url(object_path),
                    headers={"Content-Type": VIDEO_MIME_TYPE, "x-upsert": "false"},
                    content=content,
                )
        except (AppError, TimeoutError) as exc:
            # Storage may have accepted the object despite the failed response.
            # Only our unique, non-upserting path is eligible for cleanup.
            with anyio.CancelScope(shield=True):
                await self.delete_object(object_path)
            raise AppError(code="VIDEO_STORAGE_ERROR", message="The video could not be stored privately.", status_code=503) from exc
        if response.status_code == 413:
            raise AppError(code="VIDEO_STORAGE_LIMIT", message="Private Storage rejected the video size.", status_code=413)
        if not response.is_success:
            raise AppError(code="VIDEO_STORAGE_ERROR", message="The video could not be stored privately.", status_code=503)
        return StoredMedia(object_path, VIDEO_MIME_TYPE, filename[-255:])

    async def get_object(self, object_path: str) -> StoredObject:
        self.validate_object_path(object_path)
        if object_path.endswith(".mp4"):
            return await self._get_video_object(object_path)
        response = await self._request("GET", self._object_url(object_path))
        if response.status_code == 404:
            raise AppError(
                code="MEDIA_NOT_FOUND", message="Image not found.", status_code=404
            )
        if response.is_error:
            raise AppError(
                code="IMAGE_STORAGE_ERROR",
                message="The image is temporarily unavailable.",
                status_code=503,
            )
        if not response.content:
            raise AppError(
                code="MEDIA_NOT_FOUND", message="Image not found.", status_code=404
            )
        return StoredObject(
            content=response.content,
            mime_type=response.headers.get(
                "content-type", "application/octet-stream"
            ).split(";", 1)[0],
        )

    async def _get_video_object(self, object_path: str) -> StoredObject:
        limit = self.settings.max_video_upload_bytes
        timeout = self.settings.supabase_request_timeout_seconds
        try:
            with anyio.fail_after(timeout):
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    async with client.stream(
                        "GET", self._object_url(object_path),
                        headers=self._storage_headers({"Accept-Encoding": "identity"}),
                    ) as response:
                        if response.status_code == 404:
                            raise AppError(code="MEDIA_NOT_FOUND", message="Video not found.", status_code=404)
                        response.raise_for_status()
                        mime = response.headers.get("content-type", "").split(";", 1)[0]
                        if mime != VIDEO_MIME_TYPE or response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise AppError(code="INVALID_VIDEO", message="Stored video type is invalid.", status_code=422)
                        content = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if len(content) + len(chunk) > limit:
                                raise video_too_large(limit)
                            content.extend(chunk)
                        if not content:
                            raise AppError(code="MEDIA_NOT_FOUND", message="Video not found.", status_code=404)
                        return StoredObject(bytes(content), mime)
        except (httpx.HTTPError, TimeoutError) as exc:
            raise AppError(code="VIDEO_STORAGE_ERROR", message="The video is temporarily unavailable.", status_code=503) from exc

    async def object_exists(self, object_path: str) -> bool:
        try:
            await self.get_object(object_path)
        except AppError as error:
            if error.code == "MEDIA_NOT_FOUND":
                return False
            raise
        return True

    async def get_validated_object(
        self,
        object_path: str,
        *,
        expected_mime_type: str,
    ) -> StoredObject:
        """Revalidate private bytes before they cross the Meta write boundary."""

        stored = await self.get_object(object_path)
        if expected_mime_type == VIDEO_MIME_TYPE:
            if stored.mime_type != VIDEO_MIME_TYPE or len(stored.content) > self.settings.max_video_upload_bytes:
                raise AppError(code="INVALID_VIDEO", status_code=422, message="The stored video type or size is invalid.")
            await anyio.to_thread.run_sync(validate_video, stored.content)
            return stored
        expected_format = {
            "image/jpeg": "JPEG",
            "image/png": "PNG",
        }.get(expected_mime_type)
        if expected_format is None or stored.mime_type != expected_mime_type:
            raise AppError(
                code="INVALID_STORED_IMAGE",
                message="The stored image type no longer matches the validated post.",
                status_code=422,
            )
        if not stored.content or len(stored.content) > self.settings.max_upload_bytes:
            raise AppError(
                code="INVALID_STORED_IMAGE",
                message="The stored image is empty or exceeds the configured size limit.",
                status_code=422,
            )
        try:
            with Image.open(BytesIO(stored.content)) as image:
                if image.format != expected_format:
                    raise AppError(
                        code="INVALID_STORED_IMAGE",
                        message="The stored image content no longer matches its type.",
                        status_code=422,
                    )
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > self.settings.max_image_pixels:
                    raise AppError(
                        code="INVALID_STORED_IMAGE",
                        message="The stored image dimensions are invalid or too large.",
                        status_code=422,
                    )
                image.verify()
            self._decode_pixels(stored.content, expected_format)
        except AppError:
            raise
        except (
            Image.DecompressionBombError, UnidentifiedImageError, OSError,
            SyntaxError, ValueError, EOFError,
        ) as exc:
            raise AppError(
                code="INVALID_STORED_IMAGE",
                message="The stored image is not a valid JPEG or PNG image.",
                status_code=422,
            ) from exc
        return stored

    async def delete_object(self, object_path: str) -> None:
        """Best-effort rollback for an upload whose database insert failed."""

        try:
            self.validate_object_path(object_path)
            await self._request(
                "DELETE",
                self._bucket_url(object_path),
                json={"prefixes": [object_path]},
            )
        except AppError:
            return

    @staticmethod
    def validate_object_path(object_path: str) -> None:
        if not OBJECT_PATH_PATTERN.fullmatch(object_path):
            raise AppError(
                code="MEDIA_NOT_FOUND", message="Media not found.", status_code=404
            )

    async def _validate_upload(
        self, upload: UploadFile
    ) -> tuple[bytes, str, str, str]:
        original_name = (upload.filename or "").replace("\\", "/")
        display_name = Path(original_name).name
        extension = Path(display_name).suffix.lower()
        expected = ALLOWED_IMAGES.get(extension)
        if expected is None:
            raise AppError(
                code="UNSUPPORTED_IMAGE",
                message="Upload exactly one JPEG or PNG image.",
                status_code=422,
            )

        expected_mime, expected_format = expected
        if upload.content_type != expected_mime:
            raise AppError(
                code="UNSUPPORTED_IMAGE",
                message="The image extension and MIME type do not match.",
                status_code=422,
            )

        content = await upload.read(self.settings.max_upload_bytes + 1)
        if not content:
            raise AppError(
                code="EMPTY_IMAGE",
                message="The uploaded image is empty.",
                status_code=422,
            )
        if len(content) > self.settings.max_upload_bytes:
            raise AppError(
                code="IMAGE_TOO_LARGE",
                message=(
                    "Image must be no larger than "
                    f"{self.settings.max_upload_bytes} bytes."
                ),
                status_code=413,
            )

        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != expected_format:
                    raise AppError(
                        code="UNSUPPORTED_IMAGE",
                        message="The uploaded file content does not match its image type.",
                        status_code=422,
                    )
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width * height > self.settings.max_image_pixels
                ):
                    raise AppError(
                        code="INVALID_IMAGE",
                        message="The image dimensions are invalid or too large.",
                        status_code=422,
                    )
                image.verify()
            self._decode_pixels(content, expected_format)
        except AppError:
            raise
        except (
            Image.DecompressionBombError, UnidentifiedImageError, OSError,
            SyntaxError, ValueError, EOFError,
        ) as exc:
            raise AppError(
                code="INVALID_IMAGE",
                message="The uploaded file is not a valid JPEG or PNG image.",
                status_code=422,
            ) from exc

        return content, extension, expected_mime, display_name

    def _decode_pixels(self, content: bytes, expected_format: str) -> None:
        # Pillow can accept a PNG whose final IEND CRC bytes are missing.
        # Require the complete terminal chunk as well as verify() and decoding.
        if expected_format == "PNG" and not content.endswith(
            b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
        ):
            raise ValueError("Incomplete PNG ending")
        # JPEG verify() alone does not decode its pixel stream. For PNG, decode
        # every frame too, so a valid first APNG frame cannot hide corrupt data.
        with Image.open(BytesIO(content)) as decoded:
            total_pixels = 0
            for frame in range(getattr(decoded, "n_frames", 1)):
                decoded.seek(frame)
                total_pixels += decoded.width * decoded.height
                if total_pixels > self.settings.max_image_pixels:
                    raise ValueError("Decoded image exceeds the pixel limit")
                decoded.load()

    def _object_url(self, object_path: str) -> str:
        self.validate_object_path(object_path)
        encoded_path = quote(object_path, safe="/")
        return f"{self._bucket_url(object_path)}/{encoded_path}"

    def _bucket_url(self, object_path: str) -> str:
        base_url = self.settings.require_supabase_url()
        bucket_name = self.settings.supabase_video_bucket if object_path.endswith(".mp4") else self.settings.supabase_storage_bucket
        bucket = quote(bucket_name, safe="")
        return f"{base_url}/storage/v1/object/{bucket}"

    def _storage_headers(self, supplied_headers: dict[str, str]) -> dict[str, str]:
        secret_key = self.settings.require_supabase_secret_key()
        return {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
            **supplied_headers,
        }

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        headers = self._storage_headers(dict(kwargs.pop("headers", {})))
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.supabase_request_timeout_seconds, trust_env=False,
            ) as client:
                return await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise AppError(
                code="IMAGE_STORAGE_ERROR",
                message="Supabase Storage is temporarily unavailable.",
                status_code=503,
            ) from exc
