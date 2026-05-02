from fastapi import APIRouter

from ..config import get_settings
from ..models import HealthResponse, ServiceState
from ..normalizer import normalize_health
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    if not settings.mock_mode:
        snapshot = await fetch_srs_snapshot()
        return normalize_health(snapshot)

    return HealthResponse(
        status="ok",
        health_state=ServiceState.HEALTHY,
        service=settings.service_name,
        version=settings.version,
        mock_mode=settings.mock_mode,
        srs_api_url=settings.srs_api_url,
    )
