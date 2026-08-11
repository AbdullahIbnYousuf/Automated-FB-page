"""Sanitized Facebook integration failures with no raw Meta response data."""

from dataclasses import dataclass

from app.integrations.facebook.schemas import FacebookConnectionState


@dataclass(frozen=True)
class FacebookClientError(Exception):
    state: FacebookConnectionState
    safe_message: str
    meta_error_code: int | None = None

    def __str__(self) -> str:
        return self.safe_message
