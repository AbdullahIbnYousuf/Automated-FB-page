"""Safe, non-secret system configuration status."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import PublishMode, get_settings
from app.dependencies import require_operator


router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(require_operator)],
)


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


@router.get("/status", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    settings = get_settings()
    page_id_configured = settings.facebook_page_id_configured
    access_token_configured = settings.facebook_token_configured

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
            page_id_configured=page_id_configured,
            access_token_configured=access_token_configured,
            fully_configured=page_id_configured and access_token_configured,
        ),
    )
