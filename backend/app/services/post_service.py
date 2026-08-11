"""Post creation, retrieval, updates, and API mapping."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models.post import Post, PostStatus, SchedulingAttempt
from app.schemas.post import (
    PostListResponse,
    PostResponse,
    PostUpdateRequest,
    SchedulingAttemptResponse,
)
from app.services.errors import AppError
from app.services.media_service import StoredImage
from app.services.time_service import parse_local_schedule, utc_to_local_iso


def validate_caption(caption: str) -> str:
    cleaned = caption.strip()
    if not cleaned:
        raise AppError(
            code="INVALID_CAPTION",
            message="Caption is required.",
            status_code=422,
        )
    return cleaned


def validate_requested_timezone(timezone: str, settings: Settings) -> str:
    if timezone != settings.app_timezone:
        raise AppError(
            code="INVALID_TIMEZONE",
            message=f"Posts must use the configured timezone: {settings.app_timezone}.",
            status_code=422,
        )
    try:
        ZoneInfo(timezone)
    except Exception as exc:
        raise AppError(
            code="INVALID_TIMEZONE",
            message="The configured application timezone is invalid.",
            status_code=500,
        ) from exc
    return timezone


def attempt_response(attempt: SchedulingAttempt) -> SchedulingAttemptResponse:
    return SchedulingAttemptResponse(
        id=attempt.id,
        mode=attempt.mode,
        result=attempt.result,
        safe_message=attempt.safe_message,
        error_code=attempt.error_code,
        external_request_made=attempt.external_request_made,
        created_at=attempt.created_at,
        completed_at=attempt.completed_at,
    )


def post_response(post: Post) -> PostResponse:
    return PostResponse(
        id=post.id,
        caption=post.caption,
        image_url=f"/api/media/{post.image_object_path}",
        image_mime_type=post.image_mime_type,
        original_filename=post.original_filename,
        status=post.status,
        scheduled_for_utc=post.scheduled_for_utc,
        scheduled_for_local=utc_to_local_iso(
            post.scheduled_for_utc, post.display_timezone
        ),
        display_timezone=post.display_timezone,
        facebook_object_id=post.facebook_object_id,
        last_error_code=post.last_error_code,
        last_error_message=post.last_error_message,
        last_attempted_at=post.last_attempted_at,
        created_at=post.created_at,
        updated_at=post.updated_at,
        attempts=[attempt_response(attempt) for attempt in post.attempts],
    )


class PostService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create_post(
        self,
        *,
        caption: str,
        image: StoredImage,
        scheduled_for_local: str,
        timezone: str,
    ) -> PostResponse:
        cleaned_caption = validate_caption(caption)
        display_timezone = validate_requested_timezone(timezone, self.settings)
        scheduled_utc = parse_local_schedule(
            scheduled_for_local, display_timezone
        )
        post = Post(
            caption=cleaned_caption,
            image_object_path=image.object_path,
            image_mime_type=image.mime_type,
            original_filename=image.original_filename,
            status=PostStatus.DRAFT,
            scheduled_for_utc=scheduled_utc,
            display_timezone=display_timezone,
        )
        self.session.add(post)
        self.session.commit()
        return post_response(self.get_post_model(post.id))

    def list_posts(self) -> PostListResponse:
        posts = self.session.scalars(
            select(Post)
            .options(selectinload(Post.attempts))
            .order_by(Post.created_at.desc())
        ).all()
        return PostListResponse(
            items=[post_response(post) for post in posts],
            total=len(posts),
        )

    def get_post_model(self, post_id: str) -> Post:
        post = self.session.scalar(
            select(Post)
            .where(Post.id == post_id)
            .options(selectinload(Post.attempts))
        )
        if post is None:
            raise AppError(
                code="POST_NOT_FOUND",
                message="Post not found.",
                status_code=404,
            )
        return post

    def get_post(self, post_id: str) -> PostResponse:
        return post_response(self.get_post_model(post_id))

    def update_post(
        self,
        post_id: str,
        update: PostUpdateRequest,
    ) -> PostResponse:
        post = self.get_post_model(post_id)
        if post.status in {
            PostStatus.SCHEDULING,
            PostStatus.SCHEDULED,
            PostStatus.CANCELLED,
        }:
            raise AppError(
                code="INVALID_POST_STATE",
                message="This post cannot be edited in its current state.",
                status_code=409,
            )
        if update.caption is None and update.scheduled_for_local is None:
            raise AppError(
                code="VALIDATION_ERROR",
                message="Provide a caption or schedule time to update.",
                status_code=422,
            )

        if update.caption is not None:
            post.caption = validate_caption(update.caption)
        if update.scheduled_for_local is not None:
            timezone = validate_requested_timezone(
                update.timezone or post.display_timezone,
                self.settings,
            )
            post.scheduled_for_utc = parse_local_schedule(
                update.scheduled_for_local,
                timezone,
            )
            post.display_timezone = timezone

        post.status = PostStatus.DRAFT
        post.last_error_code = None
        post.last_error_message = None
        post.updated_at = datetime.now(UTC)
        self.session.commit()
        return post_response(self.get_post_model(post.id))
