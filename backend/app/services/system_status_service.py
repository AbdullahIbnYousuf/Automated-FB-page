"""The same safe status contract for the dashboard and MCP clients."""

from datetime import UTC, datetime

from pydantic import BaseModel

from app.config import PublishMode, Settings


class FacebookConfigurationStatus(BaseModel):
    page_id_configured: bool
    access_token_configured: bool
    fully_configured: bool


class SystemStatusResponse(BaseModel):
    application_mode: str
    authentication_required: bool
    supabase_configured: bool
    publish_mode: PublishMode
    automation_enabled: bool
    publishing_enabled: bool
    timezone: str
    graph_api_version: str
    facebook: FacebookConfigurationStatus
    current_time_utc: datetime


def system_status(settings: Settings) -> SystemStatusResponse:
    page = settings.facebook_page_id_configured
    token = settings.facebook_token_configured
    return SystemStatusResponse(
        application_mode=settings.application_mode,
        authentication_required=settings.auth_required,
        supabase_configured=settings.supabase_configured,
        publish_mode=settings.publish_mode,
        automation_enabled=settings.automation_enabled,
        publishing_enabled=settings.publishing_enabled,
        timezone=settings.app_timezone,
        graph_api_version=settings.facebook_graph_api_version,
        facebook=FacebookConfigurationStatus(
            page_id_configured=page, access_token_configured=token,
            fully_configured=page and token,
        ),
        current_time_utc=datetime.now(UTC),
    )
