"""Resource-oriented post creation and scheduling routes."""

from collections.abc import AsyncIterator
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as ParsedUpload
from starlette.formparsers import MultiPartException, MultiPartParser

from app.config import Settings, get_settings
from app.dependencies import get_database_session, get_media_service, require_operator
from app.models.post import SchedulingMode
from app.schemas.post import (
    PostListResponse,
    PostResponse,
    PostUpdateRequest,
    ScheduleResponse,
)
from app.services.errors import AppError
from app.services.media_service import MediaService
from app.services.post_service import PostService
from app.services.post_creation_service import create_post_from_upload
from app.services.scheduling_service import SchedulingService
from app.services.video_validation import video_too_large


router = APIRouter(
    prefix="/api/posts",
    tags=["posts"],
    dependencies=[Depends(require_operator)],
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
ApplicationSettings = Annotated[Settings, Depends(get_settings)]
ApplicationMedia = Annotated[MediaService, Depends(get_media_service)]


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    session: DatabaseSession,
    settings: ApplicationSettings,
    media_service: ApplicationMedia,
    caption: Annotated[str, Form()],
    scheduled_for_local: Annotated[str, Form()],
    timezone: Annotated[str, Form()],
    image: Annotated[UploadFile, File()],
) -> PostResponse:
    return await create_post_from_upload(
        session, settings, media_service, caption=caption, image=image,
        scheduled_for_local=scheduled_for_local, timezone=timezone,
    )


class VideoBodyTooLarge(MultiPartException):
    pass


@router.post("/video", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_video_post(
    request: Request,
    session: DatabaseSession,
    settings: ApplicationSettings,
    media_service: ApplicationMedia,
) -> PostResponse:
    # Parse only after operator authentication, and cap bytes even with no Content-Length.
    limit = settings.max_video_upload_bytes
    body_limit = limit + 65536  # Multipart headers and three small form fields.
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise AppError(code="VIDEO_FORM_INVALID", message="Send one MP4 in a multipart form.", status_code=422)
    content_length = request.headers.get("content-length")
    if content_length is not None and (not content_length.isdigit() or int(content_length) > body_limit):
        raise video_too_large(limit)

    async def bounded_body() -> AsyncIterator[bytes]:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > body_limit:
                raise VideoBodyTooLarge("Video request exceeded its byte limit.")
            yield chunk

    try:
        with anyio.fail_after(120):
            form = await MultiPartParser(
                request.headers, bounded_body(), max_files=1, max_fields=3, max_part_size=16384,
            ).parse()
    except VideoBodyTooLarge as exc:
        raise video_too_large(limit) from exc
    except TimeoutError as exc:
        raise AppError(code="VIDEO_UPLOAD_TIMEOUT", message="The video upload took too long.", status_code=408) from exc
    except MultiPartException as exc:
        raise AppError(code="VIDEO_FORM_INVALID", message="Send a caption, time, timezone, and one MP4.", status_code=422) from exc

    try:
        caption, scheduled, timezone = (form.get(field) for field in ("caption", "scheduled_for_local", "timezone"))
        upload = form.get("video")
        if (
            len(form.multi_items()) != 4 or not isinstance(upload, ParsedUpload)
            or not isinstance(caption, str) or not isinstance(scheduled, str) or not isinstance(timezone, str)
        ):
            raise AppError(code="VIDEO_FORM_INVALID", message="Send a caption, time, timezone, and one MP4.", status_code=422)
        return await create_post_from_upload(
            session, settings, media_service, caption=caption, image=upload,
            scheduled_for_local=scheduled, timezone=timezone, is_video=True,
        )
    finally:
        with anyio.CancelScope(shield=True):
            await form.close()


@router.get("", response_model=PostListResponse)
def list_posts(
    session: DatabaseSession,
    settings: ApplicationSettings,
) -> PostListResponse:
    return PostService(session, settings).list_posts()


@router.get("/{post_id}", response_model=PostResponse)
def get_post(
    post_id: str,
    session: DatabaseSession,
    settings: ApplicationSettings,
) -> PostResponse:
    return PostService(session, settings).get_post(post_id)


@router.patch("/{post_id}", response_model=PostResponse)
def update_post(
    post_id: str,
    update: PostUpdateRequest,
    session: DatabaseSession,
    settings: ApplicationSettings,
) -> PostResponse:
    return PostService(session, settings).update_post(post_id, update)


@router.post("/{post_id}/schedule", response_model=ScheduleResponse)
async def schedule_post(
    post_id: str,
    session: DatabaseSession,
    settings: ApplicationSettings,
    media_service: ApplicationMedia,
    dry_run: bool = False,
) -> ScheduleResponse:
    return await SchedulingService(
        session, settings, media_service=media_service
    ).schedule_post(post_id, requested_mode=SchedulingMode.DRY_RUN if dry_run else None)
