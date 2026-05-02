import asyncio

from backend.app.models import IngestStream, StreamMetrics, StreamProtocol, StreamStatus
from backend.app.preview_resolver import resolve_preview


def _stream(protocol: StreamProtocol, outputs: dict[str, str]) -> IngestStream:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return IngestStream(
        id="stream-1",
        name="Stream 1",
        protocol=protocol,
        status=StreamStatus.ONLINE,
        app="live",
        stream_key="stream-1",
        source_ip="203.0.113.10",
        ingest_region="unknown",
        origin_node="n1",
        started_at=now,
        last_seen_at=now,
        uptime_seconds=1,
        viewers_current=1,
        viewers_peak_1h=1,
        metrics=StreamMetrics(
            bitrate_kbps=1000,
            fps=25,
            resolution="1280x720",
            video_codec="h264",
            audio_codec="aac",
            latency_ms=None,
            packet_loss_percent=None,
            jitter_ms=None,
            keyframe_interval_seconds=None,
        ),
        outputs=outputs,
    )


def test_resolve_preview_prefers_native_hls():
    stream = _stream(StreamProtocol.RTMP, {"hls": "http://example.com/live/stream-1.m3u8"})
    result = asyncio.run(resolve_preview(stream, timeout_seconds=30))
    assert result.state == "available"
    assert result.source == "native_hls"
    assert result.playback_url is not None


def test_resolve_preview_fallback_builds_native_urls():
    stream = _stream(StreamProtocol.HLS, {})
    result = asyncio.run(resolve_preview(stream, timeout_seconds=30))
    assert result.state == "available"
    assert result.playback_url is not None
