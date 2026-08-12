"""Typed request and response contracts for persisted posts."""

from datetime import datetime

from pydantic import BaseModel

from app.models.post import AttemptResult, PostStatus, SchedulingMode


class SchedulingAttemptResponse(BaseModel):
    id: str
    mode: SchedulingMode
    result: AttemptResult
    safe_message: str
    error_code: str | None
    external_request_made: bool
    created_at: datetime
    completed_at: datetime | None


class PostResponse(BaseModel):
    id: str
    caption: str
    image_url: str
    image_mime_type: str
    original_filename: str
    status: PostStatus
    scheduled_for_utc: datetime
    scheduled_for_local: str
    display_timezone: str
    facebook_object_id: str | None
    last_error_code: str | None
    last_error_message: str | None
    last_attempted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attempts: list[SchedulingAttemptResponse]


class PostListResponse(BaseModel):
    items: list[PostResponse]
    total: int


class PostUpdateRequest(BaseModel):
    caption: str | None = None
    scheduled_for_local: str | None = None
    timezone: str | None = None


class ScheduleResponse(BaseModel):
    mode: SchedulingMode
    simulated: bool
    success: bool
    post_id: str
    attempt_id: str
    post_status: PostStatus
    external_request_made: bool
    facebook_object_id: str | None = None
    message: str


DryRunScheduleResponse = ScheduleResponse
