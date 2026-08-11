"""Image validation and path-safety tests."""

import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies import get_media_service
from app.main import app
from app.services.errors import AppError
from tests.conftest import InMemoryMediaService
from tests.helpers import create_post, image_bytes


@pytest.mark.parametrize(
    ("filename", "mime_type", "image_format"),
    [
        ("photo.jpg", "image/jpeg", "JPEG"),
        ("photo.jpeg", "image/jpeg", "JPEG"),
        ("graphic.png", "image/png", "PNG"),
    ],
)
def test_valid_jpeg_and_png_are_accepted(
    client: TestClient,
    filename: str,
    mime_type: str,
    image_format: str,
) -> None:
    response = create_post(
        client,
        filename=filename,
        mime_type=mime_type,
        content=image_bytes(image_format),
    )

    assert response.status_code == 201
    assert response.json()["image_mime_type"] == mime_type
    assert client.get(response.json()["image_url"]).status_code == 200


def test_unsupported_format_is_rejected(client: TestClient) -> None:
    response = create_post(
        client,
        filename="animation.gif",
        mime_type="image/gif",
        content=b"GIF89a",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE"


def test_empty_file_is_rejected(client: TestClient) -> None:
    response = create_post(client, content=b"")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_IMAGE"


def test_oversized_file_is_rejected(client: TestClient) -> None:
    response = create_post(
        client,
        filename="large.jpg",
        mime_type="image/jpeg",
        content=b"x" * (get_settings().max_upload_bytes + 1),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_malformed_image_is_rejected(client: TestClient) -> None:
    response = create_post(client, content=b"not a png")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


def test_path_traversal_filename_is_sanitized(
    client: TestClient, fake_media: InMemoryMediaService
) -> None:
    response = create_post(client, filename="../../outside.png")

    assert response.status_code == 201
    payload = response.json()
    assert payload["original_filename"] == "outside.png"
    object_path = payload["image_url"].removeprefix("/api/media/")
    assert re.fullmatch(r"posts/[0-9a-f-]{36}\.png", object_path)
    assert object_path in fake_media.objects


def test_stored_filename_is_server_generated(client: TestClient) -> None:
    response = create_post(client, filename="customer-photo.png")

    stored_filename = response.json()["image_url"].rsplit("/", 1)[-1]
    assert response.status_code == 201
    assert stored_filename != "customer-photo.png"
    assert re.fullmatch(r"[0-9a-f-]{36}\.png", stored_filename)


def test_storage_error_is_safely_reported(client: TestClient) -> None:
    class FailingMediaService:
        async def store_upload(self, upload):  # type: ignore[no-untyped-def]
            del upload
            raise AppError(
                code="IMAGE_STORAGE_ERROR",
                message="The image could not be stored. Try again.",
                status_code=503,
            )

    app.dependency_overrides[get_media_service] = FailingMediaService
    response = create_post(client)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "IMAGE_STORAGE_ERROR",
            "message": "The image could not be stored. Try again.",
        }
    }
    assert "test-secret-key" not in response.text
