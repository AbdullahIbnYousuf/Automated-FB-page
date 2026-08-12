"""Typed, safe Facebook connection data shared by services and API routes."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class FacebookConnectionState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    NOT_VERIFIED = "not_verified"
    CONNECTED = "connected"
    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_CREDENTIALS = "invalid_credentials"
    EXPIRED_CREDENTIALS = "expired_credentials"
    PAGE_INACCESSIBLE = "page_inaccessible"
    PAGE_MISMATCH = "page_mismatch"
    INSUFFICIENT_ACCESS = "insufficient_access"
    META_UNAVAILABLE = "meta_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    ERROR = "error"


class FacebookPageIdentity(BaseModel):
    id: str
    name: str


class FacebookScheduledPhoto(BaseModel):
    """Identifiers returned by Meta after accepting a scheduled Page photo."""

    id: str
    post_id: str | None = None

    @property
    def object_id(self) -> str:
        return self.post_id or self.id


class FacebookConnectionStatus(BaseModel):
    connected: bool
    status: FacebookConnectionState
    page_id_configured: bool
    access_token_configured: bool
    page: FacebookPageIdentity | None = None
    api_version: str
    message: str
    last_checked_at: datetime | None = None
    publishing_capability_verified: bool = False
