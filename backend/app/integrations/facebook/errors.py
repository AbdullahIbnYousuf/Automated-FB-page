"""Sanitized Facebook integration failures with no raw Meta response data."""

from dataclasses import dataclass
from enum import StrEnum

from app.integrations.facebook.schemas import FacebookConnectionState


@dataclass(frozen=True)
class FacebookClientError(Exception):
    state: FacebookConnectionState
    safe_message: str
    meta_error_code: int | None = None

    def __str__(self) -> str:
        return self.safe_message


class FacebookWriteErrorCode(StrEnum):
    CONFIGURATION = "FACEBOOK_CONFIGURATION_ERROR"
    INVALID_CREDENTIALS = "FACEBOOK_INVALID_CREDENTIALS"
    EXPIRED_CREDENTIALS = "FACEBOOK_EXPIRED_CREDENTIALS"
    PERMISSION_DENIED = "FACEBOOK_PERMISSION_DENIED"
    INVALID_SCHEDULE = "FACEBOOK_INVALID_SCHEDULE"
    INVALID_IMAGE = "FACEBOOK_INVALID_IMAGE"
    UNSUPPORTED_REQUEST = "FACEBOOK_UNSUPPORTED_REQUEST"
    PAGE_INACCESSIBLE = "FACEBOOK_PAGE_INACCESSIBLE"
    RATE_LIMITED = "FACEBOOK_RATE_LIMITED"
    META_UNAVAILABLE = "FACEBOOK_META_UNAVAILABLE"
    REJECTED = "FACEBOOK_REJECTED"
    OUTCOME_UNKNOWN = "FACEBOOK_OUTCOME_UNKNOWN"


@dataclass(frozen=True)
class FacebookWriteError(Exception):
    """Sanitized write failure; transport failures are explicitly ambiguous."""

    code: FacebookWriteErrorCode
    safe_message: str
    outcome_unknown: bool = False
    meta_error_code: int | None = None

    def __str__(self) -> str:
        return self.safe_message
