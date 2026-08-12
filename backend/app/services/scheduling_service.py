"""Scheduling orchestration with fail-closed writes and duplicate protection."""

import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.config import PublishMode, Settings
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookWriteError, FacebookWriteErrorCode
from app.models.post import (
    AttemptResult,
    Post,
    PostStatus,
    SchedulingAttempt,
    SchedulingMode,
)
from app.schemas.post import ScheduleResponse
from app.services.dry_run_scheduler import DryRunScheduler
from app.services.errors import AppError
from app.services.facebook_scheduler import FacebookScheduler
from app.services.media_service import MediaService, StoredObject
from app.services.post_service import validate_caption


logger = logging.getLogger(__name__)
CLAIMABLE_STATES = (PostStatus.DRAFT, PostStatus.READY, PostStatus.FAILED)
UNKNOWN_OUTCOME_CODE = FacebookWriteErrorCode.OUTCOME_UNKNOWN.value


class SchedulingService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        media_service: MediaService,
        dry_run_scheduler: DryRunScheduler | None = None,
        facebook_scheduler: FacebookScheduler | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.media = media_service
        self.dry_run_scheduler = dry_run_scheduler or DryRunScheduler()
        self.facebook_scheduler = facebook_scheduler or FacebookScheduler(
            FacebookClient(settings)
        )

    async def schedule_post(self, post_id: str) -> ScheduleResponse:
        mode = self._selected_mode()
        now = datetime.now(UTC)
        claimed_id = self.session.execute(
            update(Post)
            .where(
                Post.id == post_id,
                Post.status.in_(CLAIMABLE_STATES),
                or_(
                    Post.last_error_code.is_(None),
                    Post.last_error_code != UNKNOWN_OUTCOME_CODE,
                ),
            )
            .values(status=PostStatus.SCHEDULING, updated_at=now)
            .returning(Post.id)
        ).scalar_one_or_none()

        if claimed_id is None:
            current = self.session.execute(
                select(Post.status, Post.last_error_code).where(Post.id == post_id)
            ).one_or_none()
            self.session.rollback()
            if current is None:
                raise AppError(
                    code="POST_NOT_FOUND", message="Post not found.", status_code=404
                )
            current_status, last_error_code = current
            if current_status is PostStatus.SCHEDULING:
                raise AppError(
                    code="DUPLICATE_ATTEMPT_RISK",
                    message="A scheduling attempt is already in progress.",
                    status_code=409,
                )
            if last_error_code == UNKNOWN_OUTCOME_CODE:
                raise AppError(
                    code=UNKNOWN_OUTCOME_CODE,
                    message=(
                        "This post has an unknown Facebook outcome and cannot be "
                        "submitted again. Check Meta first."
                    ),
                    status_code=409,
                )
            raise AppError(
                code="INVALID_POST_STATE",
                message="This post cannot be scheduled in its current state.",
                status_code=409,
            )

        attempt = SchedulingAttempt(
            post_id=post_id,
            mode=mode,
            result=AttemptResult.IN_PROGRESS,
            safe_message=(
                "Dry-run scheduling validation is in progress."
                if mode is SchedulingMode.DRY_RUN
                else "Facebook scheduling validation is in progress."
            ),
            external_request_made=False,
            created_at=now,
        )
        self.session.add(attempt)
        self.session.commit()

        post = self._load_post(post_id)
        try:
            image = await self._validate_post(post, now=now)
            if mode is SchedulingMode.DRY_RUN:
                dry_run = self.dry_run_scheduler.schedule(post)
                return self._record_success(
                    post,
                    attempt,
                    message=dry_run.message,
                    facebook_object_id=None,
                    simulated=True,
                )

            command = self.facebook_scheduler.prepare(post, image)
            attempt.external_request_made = True
            attempt.safe_message = "Facebook scheduling request was initiated."
            self.session.commit()
            facebook = await self.facebook_scheduler.execute(command)
            return self._record_success(
                post,
                attempt,
                message=facebook.message,
                facebook_object_id=facebook.facebook_object_id,
                simulated=False,
            )
        except FacebookWriteError as exc:
            error = AppError(
                code=exc.code.value,
                message=exc.safe_message,
                status_code=502,
            )
            self._record_failure(post, attempt, error)
            logger.warning(
                "Facebook scheduling failed safely",
                extra={
                    "event": "facebook_schedule_failed",
                    "post_id": post.id,
                    "attempt_id": attempt.id,
                    "result": attempt.result.value,
                    "external_request_made": attempt.external_request_made,
                    "meta_error_code": exc.meta_error_code,
                },
            )
            raise error from exc
        except AppError as exc:
            self._record_failure(post, attempt, exc)
            raise
        except Exception as exc:
            if attempt.external_request_made:
                internal_error = AppError(
                    code=UNKNOWN_OUTCOME_CODE,
                    message=(
                        "Facebook scheduling outcome is unknown. The request may have "
                        "reached Meta; do not submit this post again until it is checked."
                    ),
                    status_code=502,
                )
            else:
                internal_error = AppError(
                    code="INTERNAL_ERROR",
                    message="Scheduling could not be completed.",
                    status_code=500,
                )
            self._record_failure(post, attempt, internal_error)
            raise internal_error from exc

    def _selected_mode(self) -> SchedulingMode:
        if self.settings.publish_mode is PublishMode.DRY_RUN:
            return SchedulingMode.DRY_RUN
        if self.settings.publishing_enabled:
            return SchedulingMode.FACEBOOK_SCHEDULE
        raise AppError(
            code="PUBLISHING_DISABLED",
            message=(
                "Facebook scheduling is blocked because automation and Facebook "
                "publish mode are not both enabled."
            ),
            status_code=503,
        )

    def _load_post(self, post_id: str) -> Post:
        post = self.session.scalar(
            select(Post)
            .where(Post.id == post_id)
            .options(selectinload(Post.attempts))
        )
        if post is None:
            raise AppError(
                code="POST_NOT_FOUND", message="Post not found.", status_code=404
            )
        return post

    async def _validate_post(self, post: Post, *, now: datetime) -> StoredObject:
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
            return await self.media.get_validated_object(
                post.image_object_path,
                expected_mime_type=post.image_mime_type,
            )
        except AppError as exc:
            if exc.code == "MEDIA_NOT_FOUND":
                raise AppError(
                    code="MISSING_IMAGE",
                    message="The stored image is missing or unreadable.",
                    status_code=422,
                ) from exc
            raise

    def _record_success(
        self,
        post: Post,
        attempt: SchedulingAttempt,
        *,
        message: str,
        facebook_object_id: str | None,
        simulated: bool,
    ) -> ScheduleResponse:
        completed_at = datetime.now(UTC)
        attempt.result = AttemptResult.SUCCESS
        attempt.safe_message = message
        attempt.completed_at = completed_at
        post.status = PostStatus.READY if simulated else PostStatus.SCHEDULED
        post.facebook_object_id = facebook_object_id
        post.last_error_code = None
        post.last_error_message = None
        post.last_attempted_at = completed_at
        post.updated_at = completed_at
        self.session.commit()
        logger.info(
            "Scheduling completed",
            extra={
                "event": "schedule_completed",
                "post_id": post.id,
                "attempt_id": attempt.id,
                "result": attempt.result.value,
                "external_request_made": attempt.external_request_made,
            },
        )
        return ScheduleResponse(
            mode=attempt.mode,
            simulated=simulated,
            success=True,
            post_id=post.id,
            attempt_id=attempt.id,
            post_status=post.status,
            external_request_made=attempt.external_request_made,
            facebook_object_id=facebook_object_id,
            message=message,
        )

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
        attempt.completed_at = completed_at
        post.status = PostStatus.FAILED
        post.last_error_code = error.code
        post.last_error_message = error.message
        post.last_attempted_at = completed_at
        post.updated_at = completed_at
        self.session.commit()
