"""Controlled serving for validated, database-referenced images."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_database_session
from app.models.post import Post
from app.services.errors import AppError
from app.services.media_service import MediaService


router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/{filename}", response_class=FileResponse)
def get_media(
    filename: str,
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    mime_type = session.scalar(
        select(Post.image_mime_type).where(Post.image_filename == filename)
    )
    if mime_type is None:
        raise AppError(
            code="MEDIA_NOT_FOUND",
            message="Image not found.",
            status_code=404,
        )
    path = MediaService(settings).resolve_stored_file(filename)
    return FileResponse(path=path, media_type=mime_type)
