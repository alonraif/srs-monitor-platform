from fastapi import APIRouter

from ..host_metrics import host_metrics_collector
from ..models import SystemResponse


router = APIRouter()


@router.get("/system", response_model=SystemResponse)
async def system() -> SystemResponse:
    return await host_metrics_collector.collect_system()
