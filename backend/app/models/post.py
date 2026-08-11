"""Local post and immutable scheduling-attempt records."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class PostStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    SCHEDULING = "scheduling"
    SCHEDULED = "scheduled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SchedulingMode(StrEnum):
    DRY_RUN = "dry_run"


class AttemptResult(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    image_object_path: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    image_mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PostStatus] = mapped_column(
        Enum(
            PostStatus,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=PostStatus.DRAFT,
        index=True,
    )
    scheduled_for_utc: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    display_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    facebook_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )

    attempts: Mapped[list["SchedulingAttempt"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        order_by=lambda: SchedulingAttempt.created_at.desc(),
    )


class SchedulingAttempt(Base):
    __tablename__ = "scheduling_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[SchedulingMode] = mapped_column(
        Enum(
            SchedulingMode,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
    )
    result: Mapped[AttemptResult] = mapped_column(
        Enum(
            AttemptResult,
            native_enum=False,
            values_callable=enum_values,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
    )
    safe_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_request_made: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )

    post: Mapped[Post] = relationship(back_populates="attempts")
