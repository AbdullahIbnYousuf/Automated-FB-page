"""Small valid-image and post-request helpers."""

from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image


def image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(46, 92, 190)).save(output, format=image_format)
    return output.getvalue()


def future_local_time(*, days: int = 1) -> str:
    value = datetime.now(ZoneInfo("Asia/Dhaka")) + timedelta(days=days)
    return value.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def create_post(
    client: TestClient,
    *,
    caption: str = "A locally managed post",
    scheduled_for_local: str | None = None,
    filename: str = "photo.png",
    mime_type: str = "image/png",
    content: bytes | None = None,
):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/posts",
        data={
            "caption": caption,
            "scheduled_for_local": scheduled_for_local or future_local_time(),
            "timezone": "Asia/Dhaka",
        },
        files={
            "image": (
                filename,
                content if content is not None else image_bytes("PNG"),
                mime_type,
            )
        },
    )
