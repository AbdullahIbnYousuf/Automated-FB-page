"""Authenticated proxy for database-referenced private post media."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_database_session, get_media_service, require_operator
from app.models.post import Post
from app.services.errors import AppError
from app.services.media_service import MediaService
from app.services.video_validation import VIDEO_MIME_TYPE


router = APIRouter(
    prefix="/api/media",
    tags=["media"],
    dependencies=[Depends(require_operator)],
)


@router.get("/{object_path:path}", response_class=Response)
async def get_media(
    object_path: str,
    session: Annotated[Session, Depends(get_database_session)],
    media_service: Annotated[MediaService, Depends(get_media_service)],
) -> Response:
    is_video = object_path.endswith(".mp4")
    if is_video:
        video_path = session.scalar(select(Post.video_object_path).where(Post.video_object_path == object_path))
        mime_type = VIDEO_MIME_TYPE if video_path else None
    else:
        mime_type = session.scalar(select(Post.image_mime_type).where(Post.image_object_path == object_path))
    if mime_type is None:
        raise AppError(
            code="MEDIA_NOT_FOUND",
            message="Media not found.",
            status_code=404,
        )
    stored_object = await media_service.get_object(object_path)
    return Response(
        content=stored_object.content,
        media_type=mime_type,
        headers={"Cache-Control": "private, no-store" if is_video else "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
