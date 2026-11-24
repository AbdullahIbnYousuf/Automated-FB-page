"""Safe, non-secret system configuration status."""

from fastapi import APIRouter, Depends
from app.config import get_settings
from app.dependencies import require_operator
from app.services.system_status_service import SystemStatusResponse, system_status as status_snapshot


router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(require_operator)],
)


class DashboardSystemStatusResponse(SystemStatusResponse):
    video_scheduling_page_id: str | None


@router.get("/status", response_model=DashboardSystemStatusResponse)
async def system_status() -> DashboardSystemStatusResponse:
    settings = get_settings()
    return DashboardSystemStatusResponse(
        **status_snapshot(settings).model_dump(),
        video_scheduling_page_id=settings.video_scheduling_page_id,
    )
