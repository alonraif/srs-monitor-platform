from fastapi import APIRouter

from ..config import get_settings
from ..mock_data import get_dashboard
from ..models import DashboardResponse
from ..normalizer import normalize_dashboard
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard() -> DashboardResponse:
    if not get_settings().mock_mode:
        snapshot = await fetch_srs_snapshot()
        return normalize_dashboard(snapshot)
    return get_dashboard()
