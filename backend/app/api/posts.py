"""Resource-oriented post and dry-run scheduling routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_database_session, get_media_service, require_operator
from app.schemas.post import (
    DryRunScheduleResponse,
    PostListResponse,
    PostResponse,
    PostUpdateRequest,
)
from app.services.media_service import MediaService
from app.services.post_service import PostService
from app.services.scheduling_service import SchedulingService


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
    stored_image = await media_service.store_upload(image)
    try:
        return PostService(session, settings).create_post(
            caption=caption,
            image=stored_image,
            scheduled_for_local=scheduled_for_local,
            timezone=timezone,
        )
    except Exception:
        await media_service.delete_object(stored_image.object_path)
        raise


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


@router.post("/{post_id}/schedule", response_model=DryRunScheduleResponse)
async def schedule_post(
    post_id: str,
    session: DatabaseSession,
    settings: ApplicationSettings,
    media_service: ApplicationMedia,
) -> DryRunScheduleResponse:
    return await SchedulingService(
        session, settings, media_service=media_service
    ).schedule_post(post_id)
