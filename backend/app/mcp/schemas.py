"""Explicit model-visible tool contracts; no tokens or signed URLs in outputs."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.mcp.files import ChatGPTFile
from app.models.post import PostStatus, SchedulingMode
from app.schemas.post import PostResponse, ScheduleResponse


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(ToolInput):
    pass


class ListPostsInput(ToolInput):
    status: PostStatus | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PostInput(ToolInput):
    post_id: str = Field(min_length=1, max_length=36)


class CreatePostInput(ToolInput):
    caption: str = Field(min_length=1)
    image: ChatGPTFile
    scheduled_for_local: str = Field(description="ISO local datetime WITHOUT offset, interpreted in timezone.")
    timezone: str = "Asia/Dhaka"
    request_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$", description="Stable unique key for this intended post; reuse on retries.")


class UpdatePostInput(PostInput):
    caption: str | None = None
    scheduled_for_local: str | None = None
    timezone: str | None = None


class SchedulePostInput(PostInput):
    mode: SchedulingMode = SchedulingMode.DRY_RUN


class CreateAndScheduleInput(CreatePostInput):
    mode: SchedulingMode = SchedulingMode.DRY_RUN


class PostSummary(BaseModel):
    id: str
    caption_preview: str
    status: PostStatus
    scheduled_for_utc: datetime
    scheduled_for_local: str
    display_timezone: str
    facebook_object_id: str | None
    last_error_code: str | None


class PostPage(BaseModel):
    items: list[PostSummary]
    total: int
    next_offset: int | None


class PostAndSchedule(BaseModel):
    post: PostResponse
    schedule: ScheduleResponse


class ToolError(BaseModel):
    code: str
    message: str
    post_id: str | None = None


T = TypeVar("T")


class ToolOutput(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ToolError | None = None
    replayed: bool = False
