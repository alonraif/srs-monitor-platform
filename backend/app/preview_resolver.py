from dataclasses import dataclass
import re
from typing import Literal
from urllib.parse import urlparse

import httpx

from .config import get_settings
from .models import IngestStream
from .preview_client import PreviewServiceClient


ResolutionState = Literal["available", "preview_started", "preview_unavailable"]
PlaybackSource = Literal["native_webrtc", "native_hls", "native_http_flv", "preview_hls", "none"]


@dataclass(frozen=True)
class PreviewResolution:
    stream_id: str
    state: ResolutionState
    source: PlaybackSource
    playback_url: str | None
    reason: str | None = None
    debug: dict | None = None


def _clean(url: str | None) -> str | None:
    if url is None:
        return None
    value = url.strip()
    return value or None


def _native_outputs(stream: IngestStream) -> tuple[str | None, str | None, str | None]:
    outputs = stream.outputs or {}
    return (
        _clean(outputs.get("webrtc")),
        _clean(outputs.get("hls")),
        _clean(outputs.get("flv") or outputs.get("http_flv")),
    )


def _publicize_native(url: str | None, kind: Literal["webrtc", "http"]) -> str | None:
    value = _clean(url)
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.hostname not in {"srs", "monitor-srs"}:
        return value

    settings = get_settings()
    if kind == "webrtc":
        base = settings.srs_public_webrtc_base_url.rstrip("/")
    else:
        base = settings.srs_public_http_base_url.rstrip("/")
    return f"{base}{parsed.path}"


def _build_fallback_native_outputs(stream: IngestStream) -> tuple[str, str, str]:
    settings = get_settings()
    app = stream.app
    key = stream.stream_key
    http_base = settings.srs_public_http_base_url.rstrip("/")
    webrtc_base = settings.srs_public_webrtc_base_url.rstrip("/")
    return (
        f"{webrtc_base}/{app}/{key}",
        f"{http_base}/{app}/{key}.m3u8",
        f"{http_base}/{app}/{key}.flv",
    )


def _derive_rewrap_input(stream: IngestStream) -> tuple[str | None, str | None]:
    # Assumption: stream app/key maps to SRS canonical publish path.
    path = f"{stream.app}/{stream.stream_key}"
    proto = stream.protocol.value.upper()

    # Assumption: SRT pull from SRS can be requested using streamid syntax when
    # subscriber mode is enabled on SRS.
    if proto == "SRT":
        return f"srt://srs:10080?streamid=#!::r={path},m=request", "srt"
    if proto == "RTMP":
        return f"rtmp://srs:1935/{path}", "rtmp"
    if proto == "HLS":
        # HLS is already browser-playable and should be handled before rewrap.
        return None, None
    if proto == "WEBRTC":
        # WebRTC is already browser-playable and should be handled before rewrap.
        return None, None
    return None, None


def _make_public_preview_url(relative_url: str | None) -> str | None:
    if not relative_url:
        return None
    settings = get_settings()
    if relative_url.startswith("http://") or relative_url.startswith("https://"):
        return relative_url
    if not SAFE_PREVIEW_PATH.fullmatch(relative_url):
        return None
    return f"{settings.preview_public_base_url.rstrip('/')}/{relative_url.lstrip('/')}"


async def _is_hls_reachable(url: str | None) -> bool:
    value = _clean(url)
    if not value:
        return False
    try:
        timeout = httpx.Timeout(2.0, connect=1.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(value)
        if response.status_code != 200:
            return False
        body = response.text[:256]
        return "#EXTM3U" in body
    except Exception:
        return False


async def resolve_preview(stream: IngestStream, timeout_seconds: int) -> PreviewResolution:
    settings = get_settings()
    prefer_webrtc = settings.preview_preferred_protocol.strip().lower() == "webrtc"
    native_webrtc, native_hls, native_flv = _native_outputs(stream)
    native_webrtc = _publicize_native(native_webrtc, "webrtc")
    native_hls = _publicize_native(native_hls, "http")
    native_flv = _publicize_native(native_flv, "http")
    if native_webrtc and not native_hls and not native_flv:
        # Some SRS snapshots provide only a WebRTC-style URL. For browser tiles
        # that use hls.js/flv.js, synthesize HTTP playback URLs from app/key.
        _, fb_hls, fb_flv = _build_fallback_native_outputs(stream)
        native_hls = native_hls or fb_hls
        native_flv = native_flv or fb_flv
    if not native_webrtc and not native_hls and not native_flv:
        fb_webrtc, fb_hls, fb_flv = _build_fallback_native_outputs(stream)
        native_webrtc = fb_webrtc
        native_hls = fb_hls
        native_flv = fb_flv

    if prefer_webrtc:
        if native_webrtc:
            return PreviewResolution(stream.id, "available", "native_webrtc", native_webrtc)
        if native_hls and await _is_hls_reachable(native_hls):
            return PreviewResolution(stream.id, "available", "native_hls", native_hls)
        if native_flv:
            return PreviewResolution(stream.id, "available", "native_http_flv", native_flv)
    else:
        if native_hls and await _is_hls_reachable(native_hls):
            return PreviewResolution(stream.id, "available", "native_hls", native_hls)
        if native_flv:
            return PreviewResolution(stream.id, "available", "native_http_flv", native_flv)
        if native_webrtc:
            return PreviewResolution(stream.id, "available", "native_webrtc", native_webrtc)

    input_url, input_protocol = _derive_rewrap_input(stream)
    if not input_url or not input_protocol:
        return PreviewResolution(
            stream.id,
            "preview_unavailable",
            "none",
            None,
            reason="no_supported_input_for_rewrap",
        )

    client = PreviewServiceClient()
    result = await client.start(
        stream_id=stream.id,
        input_url=input_url,
        input_protocol=input_protocol,
        inactivity_timeout_seconds=timeout_seconds,
    )
    if not result.reachable:
        return PreviewResolution(
            stream.id,
            "preview_unavailable",
            "none",
            None,
            reason="preview_service_unreachable",
            debug={"error": result.error},
        )
    if not result.ok:
        return PreviewResolution(
            stream.id,
            "preview_unavailable",
            "none",
            None,
            reason=result.error or "preview_service_error",
            debug={"response": result.data, "status_code": result.status_code},
        )

    state = result.data.get("state", "error")
    if state != "running":
        return PreviewResolution(
            stream.id,
            "preview_unavailable",
            "none",
            None,
            reason=result.data.get("reason") or state,
            debug={"response": result.data},
        )

    return PreviewResolution(
        stream.id,
        "preview_started",
        "preview_hls",
        _make_public_preview_url(result.data.get("preview_url")),
        debug={"response": result.data},
    )
SAFE_PREVIEW_PATH = re.compile(r"^/preview/files/[A-Za-z0-9_.:-]{1,200}/index\.m3u8$")
