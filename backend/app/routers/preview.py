from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..mock_data import get_streams
from ..models import IngestStream
from ..normalizer import normalize_streams
from ..preview_client import PreviewServiceClient
from ..preview_resolver import PreviewResolution, resolve_preview
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


class PreviewStartRequest(BaseModel):
    stream_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    inactivity_timeout_seconds: int = Field(default=60, ge=5, le=3600)


class PreviewStopRequest(BaseModel):
    stream_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]{1,200}$")


class PreviewStartResponse(BaseModel):
    stream_id: str
    state: Literal["available", "preview_started", "preview_unavailable"]
    source: str
    playback_url: str | None = None
    reason: str | None = None
    debug: dict | None = None


class PreviewStopResponse(BaseModel):
    stream_id: str
    state: str


class PreviewStatusResponse(BaseModel):
    reachable: bool
    previews: list[dict]
    error: str | None = None


def _to_response(value: PreviewResolution) -> PreviewStartResponse:
    return PreviewStartResponse(
        stream_id=value.stream_id,
        state=value.state,
        source=value.source,
        playback_url=value.playback_url,
        reason=value.reason,
        debug=value.debug,
    )


async def _source_streams() -> list[IngestStream]:
    if get_settings().mock_mode:
        return get_streams()
    snapshot = await fetch_srs_snapshot()
    return normalize_streams(snapshot)


@router.post("/preview/start", response_model=PreviewStartResponse)
async def preview_start(payload: PreviewStartRequest) -> PreviewStartResponse:
    stream = next((s for s in await _source_streams() if s.id == payload.stream_id), None)
    if stream is None:
        raise HTTPException(status_code=404, detail=f"Stream '{payload.stream_id}' not found")
    resolved = await resolve_preview(stream, timeout_seconds=payload.inactivity_timeout_seconds)
    return _to_response(resolved)


@router.post("/preview/stop", response_model=PreviewStopResponse)
async def preview_stop(payload: PreviewStopRequest) -> PreviewStopResponse:
    result = await PreviewServiceClient().stop(payload.stream_id)
    if not result.reachable:
        raise HTTPException(status_code=503, detail="preview_service_unreachable")
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error or "preview_service_error")
    return PreviewStopResponse(
        stream_id=result.data.get("stream_id", payload.stream_id),
        state=result.data.get("state", "stopped"),
    )


@router.get("/preview/status", response_model=PreviewStatusResponse)
async def preview_status() -> PreviewStatusResponse:
    result = await PreviewServiceClient().status()
    if not result.reachable:
        return PreviewStatusResponse(reachable=False, previews=[], error="preview_service_unreachable")
    if not result.ok:
        return PreviewStatusResponse(reachable=True, previews=[], error=result.error or "preview_service_error")
    previews = result.data.get("previews", [])
    if not isinstance(previews, list):
        previews = []
    return PreviewStatusResponse(reachable=True, previews=previews)


@router.get("/preview/url/{stream_id}", response_model=PreviewStartResponse)
async def preview_url(stream_id: str) -> PreviewStartResponse:
    stream = next((s for s in await _source_streams() if s.id == stream_id), None)
    if stream is None:
        return PreviewStartResponse(
            stream_id=stream_id,
            state="preview_unavailable",
            source="none",
            reason="stream_not_found",
        )
    resolved = await resolve_preview(stream, timeout_seconds=60)
    return _to_response(resolved)
