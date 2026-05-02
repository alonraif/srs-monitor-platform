import asyncio
from datetime import UTC, datetime

from backend.app.alarm_engine import AlarmEngine
from backend.app.models import (
    CapacityMetric,
    Client,
    ClientStatus,
    ExpectedStreamRecord,
    HealthResponse,
    HostHealth,
    IngestStream,
    NetworkInterface,
    ServiceState,
    StreamMetrics,
    StreamProtocol,
    StreamStatus,
)


def _now() -> datetime:
    return datetime.now(UTC)


def test_alarm_generation_expected_stream_matching():
    engine = AlarmEngine()
    expected = ExpectedStreamRecord(
        id=1,
        stream_id="feed-1",
        friendly_name="Feed 1",
        umd="UMD1",
        customer_or_event="event",
        expected_protocol="SRT",
        expected_source_ip_or_cidr="198.51.100.0/24",
        expected_min_bitrate=4000,
        expected_max_bitrate=9000,
        expected_resolution="1920x1080",
        expected_fps=50.0,
        encryption_required=True,
        priority=1,
        notes="",
        created_at=_now(),
        updated_at=_now(),
    )

    stream = IngestStream(
        id="feed-1",
        name="Feed 1",
        protocol=StreamProtocol.RTMP,
        status=StreamStatus.ONLINE,
        app="live",
        stream_key="feed-1",
        source_ip="203.0.113.20",
        ingest_region="unknown",
        origin_node="n1",
        started_at=_now(),
        last_seen_at=_now(),
        uptime_seconds=100,
        viewers_current=0,
        viewers_peak_1h=0,
        metrics=StreamMetrics(
            bitrate_kbps=2000,
            fps=30.0,
            resolution="1280x720",
            video_codec="h264",
            audio_codec="aac",
            latency_ms=None,
            packet_loss_percent=None,
            jitter_ms=None,
            keyframe_interval_seconds=None,
        ),
        outputs={},
    )
    health = HealthResponse(
        status="ok",
        health_state=ServiceState.HEALTHY,
        service="monitor-backend",
        version="0.1.0",
        mock_mode=True,
        srs_api_url="http://srs:1985",
    )
    host = HostHealth(
        hostname="host",
        status=ServiceState.HEALTHY,
        uptime_seconds=600,
        cpu_percent=10,
        load_average=[],
        memory=CapacityMetric(used=20, total=100, unit="percent"),
        disk=CapacityMetric(used=20, total=100, unit="percent"),
        network=[NetworkInterface(name="eth0", rx_mbps=1, tx_mbps=1, errors_per_minute=0)],
    )
    clients: list[Client] = []

    alarms = engine._evaluate_rules(_now(), health, [stream], clients, host, [expected])
    assert f"bitrate_too_low:{expected.stream_id}" in alarms
    assert f"unexpected_source_ip:{expected.stream_id}" in alarms
    assert f"encryption_required_missing:{expected.stream_id}" in alarms
    assert f"no_clients:{expected.stream_id}" in alarms
