"""Validated image handling backed by a private Supabase Storage bucket."""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.services.errors import AppError


ALLOWED_IMAGES = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
}
OBJECT_PATH_PATTERN = re.compile(
    r"^posts/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.(?:jpg|jpeg|png)$"
)


@dataclass(frozen=True)
class StoredImage:
    object_path: str
    mime_type: str
    original_filename: str


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

    async def get_object(self, object_path: str) -> StoredObject:
        self.validate_object_path(object_path)
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

    async def object_exists(self, object_path: str) -> bool:
        try:
            await self.get_object(object_path)
        except AppError as error:
            if error.code == "MEDIA_NOT_FOUND":
                return False
            raise
        return True

    async def delete_object(self, object_path: str) -> None:
        """Best-effort rollback for an upload whose database insert failed."""

        try:
            self.validate_object_path(object_path)
            await self._request(
                "DELETE",
                self._bucket_url(),
                json={"prefixes": [object_path]},
            )
        except AppError:
            return

    @staticmethod
    def validate_object_path(object_path: str) -> None:
        if not OBJECT_PATH_PATTERN.fullmatch(object_path):
            raise AppError(
                code="MEDIA_NOT_FOUND", message="Image not found.", status_code=404
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
        except AppError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
            raise AppError(
                code="INVALID_IMAGE",
                message="The uploaded file is not a valid JPEG or PNG image.",
                status_code=422,
            ) from exc

        return content, extension, expected_mime, display_name

    def _object_url(self, object_path: str) -> str:
        self.validate_object_path(object_path)
        base_url = self.settings.require_supabase_url()
        bucket = quote(self.settings.supabase_storage_bucket, safe="")
        encoded_path = quote(object_path, safe="/")
        return f"{base_url}/storage/v1/object/{bucket}/{encoded_path}"

    def _bucket_url(self) -> str:
        base_url = self.settings.require_supabase_url()
        bucket = quote(self.settings.supabase_storage_bucket, safe="")
        return f"{base_url}/storage/v1/object/{bucket}"

    async def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        secret_key = self.settings.require_supabase_secret_key()
        supplied_headers = dict(kwargs.pop("headers", {}))
        headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
            **supplied_headers,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.supabase_request_timeout_seconds
            ) as client:
                return await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise AppError(
                code="IMAGE_STORAGE_ERROR",
                message="Supabase Storage is temporarily unavailable.",
                status_code=503,
            ) from exc
