"""Read-only official Meta Graph API integration for Facebook Pages."""

from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.schemas import (
    FacebookConnectionState,
    FacebookConnectionStatus,
    FacebookPageIdentity,
)

__all__ = [
    "FacebookClient",
    "FacebookConnectionState",
    "FacebookConnectionStatus",
    "FacebookPageIdentity",
]
