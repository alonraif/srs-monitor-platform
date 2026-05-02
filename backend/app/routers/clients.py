from fastapi import APIRouter

from ..config import get_settings
from ..mock_data import get_clients_response
from ..models import ClientsResponse
from ..normalizer import normalize_clients_response
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


@router.get("/clients", response_model=ClientsResponse)
async def clients() -> ClientsResponse:
    if not get_settings().mock_mode:
        snapshot = await fetch_srs_snapshot()
        return normalize_clients_response(snapshot)
    return get_clients_response()
