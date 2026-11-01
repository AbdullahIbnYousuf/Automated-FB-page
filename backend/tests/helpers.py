"""Small valid-image and post-request helpers."""

from datetime import datetime, timedelta
from io import BytesIO
import zlib
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image


def image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(46, 92, 190)).save(output, format=image_format)
    return output.getvalue()


def corrupt_image_bytes(case: str) -> tuple[bytes, str, str]:
    """Keep valid headers while damaging endings or CRC-valid compressed pixels."""
    if case == "jpeg-pixels":
        return image_bytes("JPEG")[:-10], "image/jpeg", "broken.jpg"
    content = image_bytes("PNG")
    if case.startswith("png-ending-"):
        return content[:-int(case.rsplit("-", 1)[1])], "image/png", "broken.png"
    chunk_type = b"IDAT"
    if case == "apng-later-frame":
        output = BytesIO()
        first = Image.new("RGB", (8, 8), "blue")
        first.save(output, "PNG", save_all=True, append_images=[Image.new("RGB", (8, 8), "red")])
        content = output.getvalue()
        chunk_type = b"fdAT"
    offset = 8
    while offset < len(content):
        length = int.from_bytes(content[offset:offset + 4], "big")
        kind = content[offset + 4:offset + 8]
        if kind == chunk_type:
            data = content[offset + 8:offset + 8 + length]
            damaged = (data[:4] if kind == b"fdAT" else b"") + b"invalid-zlib-pixels"
            chunk = kind + damaged
            content = (
                content[:offset] + len(damaged).to_bytes(4, "big") + chunk
                + zlib.crc32(chunk).to_bytes(4, "big") + content[offset + length + 12:]
            )
            return content, "image/png", "broken.png"
        offset += length + 12
    raise AssertionError("Image fixture did not contain the intended chunk")


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
