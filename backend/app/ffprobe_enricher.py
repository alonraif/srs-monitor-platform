import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from .config import get_settings
from .models import IngestStream


JsonObject = dict[str, Any]


@dataclass
class _CacheEntry:
    expires_at: float
    fps: float | None
    scan_type: str
    debug: JsonObject


_CACHE: dict[str, _CacheEntry] = {}


def _fps_from_ratio(value: str | None) -> float | None:
    if not value:
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            num = float(left)
            den = float(right)
            if den == 0:
                return None
            return round(num / den, 3)
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def _scan_from_field_order(field_order: str | None) -> str:
    if not field_order:
        return "unknown"
    text = field_order.strip().lower()
    if text == "progressive":
        return "progressive"
    if text in {"tt", "bb", "tb", "bt", "interlaced"}:
        return "interlaced"
    return "unknown"


def _probe_urls(stream: IngestStream) -> list[str]:
    settings = get_settings()
    app = stream.app
    key = stream.stream_key
    internal = settings.srs_internal_http_base_url.rstrip("/")
    public = settings.srs_public_http_base_url.rstrip("/")
    urls = [
        f"{internal}/{app}/{key}.flv",
        f"{public}/{app}/{key}.flv",
    ]
    # Deduplicate while preserving order.
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        out.append(url)
        seen.add(url)
    return out


async def _run_ffprobe(url: str, timeout_s: float) -> JsonObject | None:
    # URL is passed as argv argument (not shell-expanded), preventing command injection.
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=field_order,avg_frame_rate,r_frame_rate",
        "-of",
        "json",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "ok": False,
            "error": "timeout",
            "url": url,
        }

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (err.decode("utf-8", errors="ignore") or "ffprobe_failed").strip()[:400],
            "url": url,
        }

    try:
        payload = json.loads(out.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "invalid_json",
            "url": url,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "unexpected_payload",
            "url": url,
        }
    return {"ok": True, "url": url, "payload": payload}


async def enrich_stream(stream: IngestStream) -> IngestStream:
    settings = get_settings()
    if settings.mock_mode or not settings.ffprobe_enabled:
        return stream

    cache_key = stream.id
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and cached.expires_at > now:
        if stream.metrics.fps is None and cached.fps is not None:
            stream.metrics.fps = cached.fps
        if stream.metrics.scan_type == "unknown" and cached.scan_type in {"interlaced", "progressive"}:
            stream.metrics.scan_type = cached.scan_type
        stream.debug = stream.debug or {}
        stream.debug["ffprobe"] = cached.debug
        return stream

    timeout_s = settings.ffprobe_timeout_seconds
    urls = _probe_urls(stream)
    best_debug: JsonObject = {"attempts": []}
    fps: float | None = None
    scan_type = "unknown"

    for url in urls:
        result = await _run_ffprobe(url, timeout_s)
        if result is None:
            continue
        best_debug["attempts"].append(result)
        if not result.get("ok"):
            continue
        payload = result.get("payload")
        streams = payload.get("streams") if isinstance(payload, dict) else None
        first = streams[0] if isinstance(streams, list) and streams and isinstance(streams[0], dict) else {}
        fps = _fps_from_ratio(first.get("avg_frame_rate")) or _fps_from_ratio(first.get("r_frame_rate"))
        scan_type = _scan_from_field_order(first.get("field_order"))
        best_debug["selected_url"] = url
        best_debug["video_stream"] = first
        break

    _CACHE[cache_key] = _CacheEntry(
        expires_at=now + settings.ffprobe_cache_ttl_seconds,
        fps=fps,
        scan_type=scan_type,
        debug=best_debug,
    )

    if stream.metrics.fps is None and fps is not None:
        stream.metrics.fps = fps
    if stream.metrics.scan_type == "unknown" and scan_type in {"progressive", "interlaced"}:
        stream.metrics.scan_type = scan_type
    stream.debug = stream.debug or {}
    stream.debug["ffprobe"] = best_debug
    return stream


async def enrich_streams(streams: list[IngestStream]) -> list[IngestStream]:
    if not streams:
        return streams
    tasks = [enrich_stream(stream) for stream in streams]
    return await asyncio.gather(*tasks)
