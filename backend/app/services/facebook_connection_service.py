"""Backend-authoritative orchestration for read-only Facebook checks."""

import logging
from datetime import UTC, datetime

from app.config import Settings
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.errors import FacebookClientError
from app.integrations.facebook.schemas import (
    FacebookConnectionState,
    FacebookConnectionStatus,
)


logger = logging.getLogger(__name__)


class FacebookConnectionService:
    """Test Page access and retain only a safe process-local result."""

    def __init__(self, settings: Settings, client: FacebookClient) -> None:
        self._settings = settings
        self._client = client
        self._last_result: FacebookConnectionStatus | None = None
        self._last_page_id: str | None = None
        self._last_api_version: str | None = None

    def get_status(self) -> FacebookConnectionStatus:
        page_configured = self._settings.facebook_page_id_configured
        token_configured = self._settings.facebook_token_configured
        api_version = self._settings.facebook_graph_api_version.strip()

        if not page_configured or not token_configured:
            return FacebookConnectionStatus(
                connected=False,
                status=FacebookConnectionState.NOT_CONFIGURED,
                page_id_configured=page_configured,
                access_token_configured=token_configured,
                api_version=api_version,
                message="Facebook Page credentials are not fully configured.",
            )

        configured_page_id = (self._settings.facebook_page_id or "").strip()
        if (
            self._last_result is not None
            and self._last_page_id == configured_page_id
            and self._last_api_version == api_version
        ):
            return self._last_result

        return FacebookConnectionStatus(
            connected=False,
            status=FacebookConnectionState.NOT_VERIFIED,
            page_id_configured=True,
            access_token_configured=True,
            api_version=api_version,
            message="Facebook Page credentials are configured but not verified.",
        )

    async def test_connection(self) -> FacebookConnectionStatus:
        current_status = self.get_status()
        if current_status.status is FacebookConnectionState.NOT_CONFIGURED:
            return current_status

        checked_at = datetime.now(UTC)
        try:
            page = await self._client.get_page_identity()
            result = FacebookConnectionStatus(
                connected=True,
                status=FacebookConnectionState.CONNECTED,
                page_id_configured=True,
                access_token_configured=True,
                page=page,
                api_version=self._settings.facebook_graph_api_version.strip(),
                message=(
                    "Facebook Page connection verified. "
                    "Publishing capability has not yet been proven."
                ),
                last_checked_at=checked_at,
            )
        except FacebookClientError as error:
            logger.warning(
                "Facebook connection test failed safely",
                extra={
                    "event": "facebook_connection_test",
                    "facebook_status": error.state.value,
                    "meta_error_code": error.meta_error_code,
                },
            )
            result = FacebookConnectionStatus(
                connected=False,
                status=error.state,
                page_id_configured=self._settings.facebook_page_id_configured,
                access_token_configured=self._settings.facebook_token_configured,
                api_version=self._settings.facebook_graph_api_version.strip(),
                message=error.safe_message,
                last_checked_at=checked_at,
            )

        self._last_result = result
        self._last_page_id = (self._settings.facebook_page_id or "").strip()
        self._last_api_version = self._settings.facebook_graph_api_version.strip()
        return result
