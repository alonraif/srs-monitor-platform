import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..alarm_engine import alarm_engine
from ..config import get_settings
from ..ffprobe_enricher import enrich_streams
from ..mock_data import get_dashboard, get_streams_response
from ..normalizer import normalize_dashboard, normalize_stream_summary, normalize_streams
from ..preview_client import PreviewServiceClient
from ..srs_client import fetch_srs_snapshot


router = APIRouter()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _preview_status_payload() -> dict[str, Any]:
    result = await PreviewServiceClient().status()
    if not result.reachable:
        return {"reachable": False, "previews": [], "error": "preview_service_unreachable"}
    if not result.ok:
        return {"reachable": True, "previews": [], "error": result.error or "preview_service_error"}
    previews = result.data.get("previews", [])
    if not isinstance(previews, list):
        previews = []
    return {"reachable": True, "previews": previews, "error": None}


async def _live_snapshot() -> dict[str, Any]:
    settings = get_settings()
    if settings.mock_mode:
        dashboard = get_dashboard().model_dump(mode="json")
        streams = get_streams_response().model_dump(mode="json")
    else:
        snapshot = await fetch_srs_snapshot()
        normalized_streams = normalize_streams(snapshot)
        enriched = await enrich_streams(normalized_streams)
        dashboard_model = normalize_dashboard(snapshot)
        dashboard_model.stream_summary = normalize_stream_summary(enriched)
        dashboard_model.top_streams = sorted(enriched, key=lambda stream: stream.viewers_current, reverse=True)[:3]
        dashboard = dashboard_model.model_dump(mode="json")
        streams = {
            "generated_at": _now_iso(),
            "total": len(enriched),
            "streams": [stream.model_dump(mode="json") for stream in enriched],
        }

    alarms = (await alarm_engine.evaluate_and_list()).model_dump(mode="json")
    preview = await _preview_status_payload()
    return {
        "generated_at": _now_iso(),
        "dashboard": dashboard,
        "streams": streams,
        "alarms": alarms,
        "preview": preview,
    }


@router.get("/live")
async def live() -> StreamingResponse:
    async def event_stream():
        while True:
            payload = await _live_snapshot()
            yield f"event: live\ndata: {json.dumps(payload)}\n\n"
            yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
