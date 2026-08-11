"""Controlled local image validation, storage, and lookup."""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.services.errors import AppError


ALLOWED_IMAGES = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
}
STORED_FILENAME_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.(?:jpg|jpeg|png)$"
)


@dataclass(frozen=True)
class StoredImage:
    filename: str
    mime_type: str
    original_filename: str


class MediaService:
    def __init__(self, settings: Settings) -> None:
        self.upload_directory = settings.upload_directory.expanduser().resolve()
        self.max_upload_bytes = settings.max_upload_bytes
        self.max_image_pixels = settings.max_image_pixels

    async def store_upload(self, upload: UploadFile) -> StoredImage:
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

        content = await upload.read(self.max_upload_bytes + 1)
        if not content:
            raise AppError(
                code="EMPTY_IMAGE",
                message="The uploaded image is empty.",
                status_code=422,
            )
        if len(content) > self.max_upload_bytes:
            raise AppError(
                code="IMAGE_TOO_LARGE",
                message=f"Image must be no larger than {self.max_upload_bytes} bytes.",
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
                if width <= 0 or height <= 0 or width * height > self.max_image_pixels:
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

        self.upload_directory.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid4()}{extension}"
        target = (self.upload_directory / stored_filename).resolve()
        if target.parent != self.upload_directory:
            raise AppError(
                code="INVALID_IMAGE_PATH",
                message="The image could not be stored safely.",
                status_code=500,
            )
        try:
            with target.open("xb") as output:
                output.write(content)
        except FileExistsError as exc:
            raise AppError(
                code="IMAGE_STORAGE_CONFLICT",
                message="The image could not be stored safely. Try again.",
                status_code=409,
            ) from exc

        return StoredImage(
            filename=stored_filename,
            mime_type=expected_mime,
            original_filename=display_name or f"upload{extension}",
        )

    def resolve_stored_file(self, filename: str) -> Path:
        if not STORED_FILENAME_PATTERN.fullmatch(filename):
            raise AppError(
                code="MEDIA_NOT_FOUND",
                message="Image not found.",
                status_code=404,
            )
        path = (self.upload_directory / filename).resolve()
        if path.parent != self.upload_directory or not path.is_file():
            raise AppError(
                code="MEDIA_NOT_FOUND",
                message="Image not found.",
                status_code=404,
            )
        return path

    def delete_stored_file(self, filename: str) -> None:
        try:
            path = self.resolve_stored_file(filename)
        except AppError:
            return
        path.unlink(missing_ok=True)
