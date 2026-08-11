"""Protected, read-only Facebook Page connection endpoints."""

from fastapi import APIRouter, Depends

from app.dependencies import get_facebook_connection_service, require_operator
from app.integrations.facebook.schemas import FacebookConnectionStatus
from app.services.facebook_connection_service import FacebookConnectionService


router = APIRouter(
    prefix="/api/facebook",
    tags=["facebook"],
    dependencies=[Depends(require_operator)],
)


@router.get("/status", response_model=FacebookConnectionStatus)
async def facebook_status(
    service: FacebookConnectionService = Depends(get_facebook_connection_service),
) -> FacebookConnectionStatus:
    return service.get_status()


@router.post("/test-connection", response_model=FacebookConnectionStatus)
async def test_facebook_connection(
    service: FacebookConnectionService = Depends(get_facebook_connection_service),
) -> FacebookConnectionStatus:
    return await service.test_connection()
