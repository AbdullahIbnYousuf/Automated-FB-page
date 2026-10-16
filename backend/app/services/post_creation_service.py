"""One private-image and database creation workflow for REST and MCP."""

from collections.abc import Callable

import anyio
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import Settings
from app.schemas.post import PostResponse
from app.services.media_service import MediaService
from app.services.post_service import PostService, validate_caption, validate_requested_timezone
from app.services.time_service import parse_local_schedule


async def create_post_from_upload(
    session: Session, settings: Settings, media: MediaService, *,
    caption: str, scheduled_for_local: str, timezone: str, image: UploadFile,
    before_commit: Callable[[str], None] | None = None,
) -> PostResponse:
    validate_caption(caption)
    validate_requested_timezone(timezone, settings)
    parse_local_schedule(scheduled_for_local, timezone)
    stored = await media.store_upload(image)
    try:
        post = PostService(session, settings).create_post(
            caption=caption, image=stored, scheduled_for_local=scheduled_for_local,
            timezone=timezone, commit=False,
        )
        if before_commit:
            before_commit(post.id)
        session.commit()
        return post
    except BaseException:
        session.rollback()
        with anyio.CancelScope(shield=True):
            await media.delete_object(stored.object_path)
        raise
