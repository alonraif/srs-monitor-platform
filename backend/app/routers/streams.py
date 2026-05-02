from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..ffprobe_enricher import enrich_streams
from ..mock_data import get_streams, get_streams_response
from ..models import IngestStream, StreamsResponse
from ..normalizer import normalize_streams
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


@router.get("/streams", response_model=StreamsResponse)
async def streams() -> StreamsResponse:
    if not get_settings().mock_mode:
        snapshot = await fetch_srs_snapshot()
        source_streams = normalize_streams(snapshot)
        enriched = await enrich_streams(source_streams)
        return StreamsResponse(
            generated_at=datetime.now(UTC).replace(microsecond=0),
            total=len(enriched),
            streams=enriched,
        )
    return get_streams_response()


@router.get("/streams/{id}", response_model=IngestStream)
async def stream_detail(id: str) -> IngestStream:
    if get_settings().mock_mode:
        source_streams = get_streams()
    else:
        snapshot = await fetch_srs_snapshot()
        source_streams = normalize_streams(snapshot)
        source_streams = await enrich_streams(source_streams)

    for stream in source_streams:
        if stream.id == id:
            return stream
    raise HTTPException(status_code=404, detail=f"Stream '{id}' was not found")
