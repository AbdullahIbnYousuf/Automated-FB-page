"""Inspect bounded MP4 inputs without transcoding or opening external resources."""

from io import BytesIO

import av

from app.services.errors import AppError


VIDEO_MIME_TYPE = "video/mp4"


def video_too_large(limit: int) -> AppError:
    return AppError(
        code="VIDEO_TOO_LARGE", message=f"Video must be no larger than {limit} bytes.",
        status_code=413,
    )


def _deny_external_io(*_args: object) -> None:
    raise OSError("External media references are not supported.")


def _verify_box_bounds(content: bytes) -> None:
    """Reject truncated top-level boxes even when the demuxer tolerates them."""
    required = {b"moov", b"mdat"}
    offset = 0
    while offset < len(content):
        if len(content) - offset < 8:
            raise ValueError
        size = int.from_bytes(content[offset:offset + 4], "big")
        kind = content[offset + 4:offset + 8]
        header = 8
        if size == 1:
            header = 16
            if len(content) - offset < header:
                raise ValueError
            size = int.from_bytes(content[offset + 8:offset + 16], "big")
        elif size == 0:
            size = len(content) - offset
        if size < header or offset + size > len(content):
            raise ValueError
        required.discard(kind)
        offset += size
    if required:
        raise ValueError


def validate_video(content: bytes) -> None:
    try:
        if len(content) < 16 or content[4:8] != b"ftyp" or content[8:12] == b"qt  ":
            raise ValueError
        _verify_box_bounds(content)
        with av.logging.Capture(), av.open(
            BytesIO(content), format="mov", io_open=_deny_external_io,
            container_options={"enable_drefs": "0", "use_absolute_path": "0"},
        ) as container:
            videos = container.streams.video
            audio = container.streams.audio
            if (
                len(videos) != 1 or len(audio) > 1
                or len(container.streams) != len(videos) + len(audio)
                or videos[0].codec_context.name != "h264"
                or any(stream.codec_context.name != "aac" for stream in audio)
                or not container.duration or container.duration < 0
            ):
                raise ValueError
            have_video = False
            for packet in container.demux(videos[0]):
                if packet.is_corrupt:
                    raise ValueError
                if packet.size > 0:
                    have_video = True
            if not have_video:
                raise ValueError
    except (av.FFmpegError, ValueError, OSError) as exc:
        raise AppError(
            code="INVALID_VIDEO", status_code=422,
            message="Upload a valid MP4 with H.264 video and optional AAC audio.",
        ) from exc
