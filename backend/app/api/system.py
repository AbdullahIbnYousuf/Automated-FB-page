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


@router.get("/status", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    return status_snapshot(get_settings())
