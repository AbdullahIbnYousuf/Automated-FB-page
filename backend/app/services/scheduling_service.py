"""Scheduling orchestration with atomic duplicate-attempt protection."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.config import PublishMode, Settings
from app.models.post import (
    AttemptResult,
    Post,
    PostStatus,
    SchedulingAttempt,
    SchedulingMode,
)
from app.schemas.post import DryRunScheduleResponse
from app.services.dry_run_scheduler import DryRunScheduler
from app.services.errors import AppError
from app.services.media_service import MediaService
from app.services.post_service import validate_caption


CLAIMABLE_STATES = (
    PostStatus.DRAFT,
    PostStatus.READY,
    PostStatus.FAILED,
)


class SchedulingService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        dry_run_scheduler: DryRunScheduler | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.media = MediaService(settings)
        self.dry_run_scheduler = dry_run_scheduler or DryRunScheduler()

    def schedule_post(self, post_id: str) -> DryRunScheduleResponse:
        if self.settings.publish_mode is not PublishMode.DRY_RUN:
            raise AppError(
                code="CONFIGURATION_ERROR",
                message="Real Facebook scheduling is not implemented. Use dry-run mode.",
                status_code=503,
            )

        now = datetime.now(UTC)
        claimed_id = self.session.execute(
            update(Post)
            .where(Post.id == post_id, Post.status.in_(CLAIMABLE_STATES))
            .values(status=PostStatus.SCHEDULING, updated_at=now)
            .returning(Post.id)
        ).scalar_one_or_none()

        if claimed_id is None:
            current_status = self.session.scalar(
                select(Post.status).where(Post.id == post_id)
            )
            self.session.rollback()
            if current_status is None:
                raise AppError(
                    code="POST_NOT_FOUND",
                    message="Post not found.",
                    status_code=404,
                )
            if current_status is PostStatus.SCHEDULING:
                raise AppError(
                    code="DUPLICATE_ATTEMPT_RISK",
                    message="A scheduling attempt is already in progress.",
                    status_code=409,
                )
            raise AppError(
                code="INVALID_POST_STATE",
                message="This post cannot be scheduled in its current state.",
                status_code=409,
            )

        attempt = SchedulingAttempt(
            post_id=post_id,
            mode=SchedulingMode.DRY_RUN,
            result=AttemptResult.IN_PROGRESS,
            safe_message="Dry-run scheduling validation is in progress.",
            external_request_made=False,
            created_at=now,
        )
        self.session.add(attempt)
        self.session.commit()

        post = self._load_post(post_id)
        try:
            self._validate_post(post, now=now)
            result = self.dry_run_scheduler.schedule(post)
            completed_at = datetime.now(UTC)
            attempt.result = AttemptResult.SUCCESS
            attempt.safe_message = result.message
            attempt.external_request_made = result.external_request_made
            attempt.completed_at = completed_at
            post.status = PostStatus.READY
            post.last_error_code = None
            post.last_error_message = None
            post.last_attempted_at = completed_at
            post.updated_at = completed_at
            self.session.commit()
        except AppError as exc:
            self._record_failure(post, attempt, exc)
            raise
        except Exception:
            internal_error = AppError(
                code="INTERNAL_ERROR",
                message="Dry-run scheduling could not be completed.",
                status_code=500,
            )
            self._record_failure(post, attempt, internal_error)
            raise

        return DryRunScheduleResponse(
            mode=SchedulingMode.DRY_RUN,
            simulated=True,
            success=True,
            post_id=post.id,
            attempt_id=attempt.id,
            post_status=post.status,
            external_request_made=attempt.external_request_made,
            message=attempt.safe_message,
        )

    def _load_post(self, post_id: str) -> Post:
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

    def _validate_post(self, post: Post, *, now: datetime) -> None:
        validate_caption(post.caption)
        if post.scheduled_for_utc.tzinfo is None:
            raise AppError(
                code="INVALID_SCHEDULE",
                message="Stored schedule time is invalid.",
                status_code=422,
            )
        if post.scheduled_for_utc <= now:
            raise AppError(
                code="INVALID_SCHEDULE",
                message="Schedule time must still be in the future.",
                status_code=422,
            )
        try:
            path = self.media.resolve_stored_file(post.image_filename)
            with path.open("rb") as image:
                if not image.read(1):
                    raise OSError("empty image")
        except (AppError, OSError) as exc:
            raise AppError(
                code="MISSING_IMAGE",
                message="The stored image is missing or unreadable.",
                status_code=422,
            ) from exc

    def _record_failure(
        self,
        post: Post,
        attempt: SchedulingAttempt,
        error: AppError,
    ) -> None:
        completed_at = datetime.now(UTC)
        attempt.result = AttemptResult.FAILED
        attempt.safe_message = error.message
        attempt.error_code = error.code
        attempt.external_request_made = False
        attempt.completed_at = completed_at
        post.status = PostStatus.FAILED
        post.last_error_code = error.code
        post.last_error_message = error.message
        post.last_attempted_at = completed_at
        post.updated_at = completed_at
        self.session.commit()
