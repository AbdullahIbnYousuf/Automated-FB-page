"""Single-purpose adapter for one scheduled Facebook Page photo."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.schemas import FacebookScheduledPhoto
from app.models.post import Post
from app.services.errors import AppError
from app.services.media_service import StoredObject


MINIMUM_SCHEDULE_DELAY = timedelta(minutes=10)
MAXIMUM_SCHEDULE_DELAY = timedelta(days=30)
MINIMUM_BOUNDARY_BUFFER = timedelta(seconds=30)


@dataclass(frozen=True)
class FacebookScheduleCommand:
    caption: str
    image_content: bytes
    image_mime_type: str
    scheduled_publish_time: int


@dataclass(frozen=True)
class FacebookScheduleResult:
    facebook_object_id: str
    message: str = "Facebook accepted this post for scheduled publication."


class FacebookScheduler:
    """Prepare locally, then execute exactly one external Meta write."""

    def __init__(self, client: FacebookClient) -> None:
        self.client = client

    def prepare(
        self,
        post: Post,
        image: StoredObject,
        *,
        now: datetime | None = None,
    ) -> FacebookScheduleCommand:
        self.client.configuration(for_write=True)
        checked_at = (now or datetime.now(UTC)).astimezone(UTC)
        scheduled_at = post.scheduled_for_utc.astimezone(UTC)

        if scheduled_at < checked_at + MINIMUM_SCHEDULE_DELAY + MINIMUM_BOUNDARY_BUFFER:
            raise AppError(
                code="FACEBOOK_SCHEDULE_TOO_SOON",
                message=(
                    "Facebook scheduling requires a time at least 10 minutes in "
                    "the future; choose a slightly later time for request processing."
                ),
                status_code=422,
            )
        if scheduled_at > checked_at + MAXIMUM_SCHEDULE_DELAY:
            raise AppError(
                code="FACEBOOK_SCHEDULE_TOO_FAR",
                message="Facebook scheduling supports times no more than 30 days ahead.",
                status_code=422,
            )

        return FacebookScheduleCommand(
            caption=post.caption,
            image_content=image.content,
            image_mime_type=post.image_mime_type,
            scheduled_publish_time=int(scheduled_at.timestamp()),
        )

    async def execute(
        self, command: FacebookScheduleCommand
    ) -> FacebookScheduleResult:
        response: FacebookScheduledPhoto = await self.client.schedule_page_photo(
            caption=command.caption,
            image_content=command.image_content,
            image_mime_type=command.image_mime_type,
            scheduled_publish_time=command.scheduled_publish_time,
        )
        return FacebookScheduleResult(facebook_object_id=response.object_id)
