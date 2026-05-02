from datetime import UTC, datetime, timedelta

from .config import get_settings
from .models import (
    Alarm,
    AlarmSeverity,
    AlarmStatus,
    AlarmsResponse,
    CapacityMetric,
    Client,
    ClientStatus,
    ClientsResponse,
    DashboardResponse,
    HostHealth,
    IngestStream,
    NetworkInterface,
    ServiceHealth,
    ServiceState,
    SrsHealth,
    StreamMetrics,
    StreamProtocol,
    StreamStatus,
    StreamSummary,
    StreamsResponse,
    SystemResponse,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def get_streams() -> list[IngestStream]:
    now = _now()
    return [
        IngestStream(
            id="ingest-main-001",
            name="Main Program Feed",
            protocol=StreamProtocol.SRT,
            status=StreamStatus.ONLINE,
            app="live",
            stream_key="main-program",
            source_ip="203.0.113.21",
            ingest_region="us-east-1",
            origin_node="srs-origin-01",
            started_at=now - timedelta(hours=6, minutes=18),
            last_seen_at=now - timedelta(seconds=2),
            uptime_seconds=22680,
            viewers_current=1842,
            viewers_peak_1h=2310,
            metrics=StreamMetrics(
                bitrate_kbps=8200,
                fps=59.94,
                scan_type="progressive",
                resolution="1920x1080",
                video_codec="H.264 High",
                audio_codec="AAC-LC 48kHz",
                latency_ms=740,
                packet_loss_percent=0.02,
                jitter_ms=8,
                keyframe_interval_seconds=2.0,
            ),
            outputs={
                "flv": "http://srs:8080/live/main-program.flv",
                "hls": "http://srs:8080/live/main-program.m3u8",
                "webrtc": "webrtc://srs/live/main-program",
            },
            tags=["primary", "sports", "production"],
        ),
        IngestStream(
            id="ingest-studio-002",
            name="Studio A Return",
            protocol=StreamProtocol.RTMP,
            status=StreamStatus.DEGRADED,
            app="studio",
            stream_key="studio-a-return",
            source_ip="198.51.100.44",
            ingest_region="us-west-2",
            origin_node="srs-origin-02",
            started_at=now - timedelta(hours=1, minutes=41),
            last_seen_at=now - timedelta(seconds=4),
            uptime_seconds=6060,
            viewers_current=312,
            viewers_peak_1h=488,
            metrics=StreamMetrics(
                bitrate_kbps=4100,
                fps=29.97,
                scan_type="interlaced",
                resolution="1280x720",
                video_codec="H.264 Main",
                audio_codec="AAC-LC 44.1kHz",
                latency_ms=1850,
                packet_loss_percent=1.74,
                jitter_ms=47,
                keyframe_interval_seconds=2.0,
            ),
            outputs={
                "flv": "http://srs:8080/studio/studio-a-return.flv",
                "hls": "http://srs:8080/studio/studio-a-return.m3u8",
            },
            tags=["return", "studio-a"],
        ),
        IngestStream(
            id="ingest-camera-003",
            name="Venue Camera 3",
            protocol=StreamProtocol.WEBRTC,
            status=StreamStatus.ONLINE,
            app="remote",
            stream_key="venue-camera-3",
            source_ip="203.0.113.87",
            ingest_region="eu-central-1",
            origin_node="srs-edge-03",
            started_at=now - timedelta(minutes=52),
            last_seen_at=now - timedelta(seconds=1),
            uptime_seconds=3120,
            viewers_current=96,
            viewers_peak_1h=121,
            metrics=StreamMetrics(
                bitrate_kbps=2600,
                fps=30.0,
                scan_type="progressive",
                resolution="1280x720",
                video_codec="H.264 Baseline",
                audio_codec="Opus 48kHz",
                latency_ms=290,
                packet_loss_percent=0.15,
                jitter_ms=13,
                keyframe_interval_seconds=1.0,
            ),
            outputs={
                "webrtc": "webrtc://srs/remote/venue-camera-3",
                "hls": "http://srs:8080/remote/venue-camera-3.m3u8",
            },
            tags=["remote", "low-latency"],
        ),
        IngestStream(
            id="ingest-backup-004",
            name="Backup Program Feed",
            protocol=StreamProtocol.HLS,
            status=StreamStatus.OFFLINE,
            app="backup",
            stream_key="program-backup",
            source_ip="192.0.2.18",
            ingest_region="us-east-1",
            origin_node="srs-origin-01",
            started_at=None,
            last_seen_at=now - timedelta(minutes=17, seconds=34),
            uptime_seconds=0,
            viewers_current=0,
            viewers_peak_1h=0,
            metrics=StreamMetrics(
                bitrate_kbps=0,
                fps=0,
                scan_type="unknown",
                resolution="1920x1080",
                video_codec="H.265 Main",
                audio_codec="AAC-LC 48kHz",
                latency_ms=0,
                packet_loss_percent=0,
                jitter_ms=0,
                keyframe_interval_seconds=2.0,
            ),
            outputs={
                "hls": "http://srs:8080/backup/program-backup.m3u8",
            },
            tags=["backup", "standby"],
        ),
        IngestStream(
            id="ingest-news-005",
            name="Newsroom Live Shot",
            protocol=StreamProtocol.SRT,
            status=StreamStatus.ONLINE,
            app="news",
            stream_key="newsroom-live",
            source_ip="198.51.100.73",
            ingest_region="ap-southeast-1",
            origin_node="srs-edge-05",
            started_at=now - timedelta(hours=3, minutes=7),
            last_seen_at=now - timedelta(seconds=3),
            uptime_seconds=11220,
            viewers_current=524,
            viewers_peak_1h=792,
            metrics=StreamMetrics(
                bitrate_kbps=5600,
                fps=50.0,
                scan_type="interlaced",
                resolution="1920x1080",
                video_codec="H.264 High",
                audio_codec="AAC-LC 48kHz",
                latency_ms=980,
                packet_loss_percent=0.08,
                jitter_ms=19,
                keyframe_interval_seconds=2.0,
            ),
            outputs={
                "flv": "http://srs:8080/news/newsroom-live.flv",
                "hls": "http://srs:8080/news/newsroom-live.m3u8",
            },
            tags=["news", "remote"],
        ),
    ]


def get_clients() -> list[Client]:
    now = _now()
    return [
        Client(
            id="client-7f32a1",
            stream_id="ingest-main-001",
            stream_name="Main Program Feed",
            protocol=StreamProtocol.HLS,
            status=ClientStatus.CONNECTED,
            ip="198.51.100.201",
            country="US",
            city="New York",
            user_agent="Mozilla/5.0 AppleWebKit/537.36 Chrome/124",
            player="hls.js",
            connected_at=now - timedelta(minutes=42),
            duration_seconds=2520,
            bitrate_kbps=6100,
            buffer_health_seconds=18.4,
            dropped_frames=0,
        ),
        Client(
            id="client-a91c20",
            stream_id="ingest-main-001",
            stream_name="Main Program Feed",
            protocol=StreamProtocol.WEBRTC,
            status=ClientStatus.CONNECTED,
            ip="203.0.113.145",
            country="GB",
            city="London",
            user_agent="Mozilla/5.0 AppleWebKit/605.1.15 Safari/17",
            player="native-webrtc",
            connected_at=now - timedelta(minutes=9, seconds=21),
            duration_seconds=561,
            bitrate_kbps=4200,
            buffer_health_seconds=4.1,
            dropped_frames=3,
        ),
        Client(
            id="client-0c4e10",
            stream_id="ingest-studio-002",
            stream_name="Studio A Return",
            protocol=StreamProtocol.HLS,
            status=ClientStatus.BUFFERING,
            ip="192.0.2.94",
            country="DE",
            city="Frankfurt",
            user_agent="Mozilla/5.0 AppleWebKit/537.36 Edge/124",
            player="video.js",
            connected_at=now - timedelta(minutes=16, seconds=4),
            duration_seconds=964,
            bitrate_kbps=2200,
            buffer_health_seconds=1.2,
            dropped_frames=128,
        ),
        Client(
            id="client-d561bf",
            stream_id="ingest-camera-003",
            stream_name="Venue Camera 3",
            protocol=StreamProtocol.WEBRTC,
            status=ClientStatus.CONNECTED,
            ip="203.0.113.188",
            country="JP",
            city="Tokyo",
            user_agent="Mozilla/5.0 AppleWebKit/537.36 Chrome/123",
            player="native-webrtc",
            connected_at=now - timedelta(minutes=3, seconds=18),
            duration_seconds=198,
            bitrate_kbps=2500,
            buffer_health_seconds=3.6,
            dropped_frames=1,
        ),
    ]


def get_alarms() -> list[Alarm]:
    now = _now()
    return [
        Alarm(
            id="alarm-1001",
            severity=AlarmSeverity.WARNING,
            status=AlarmStatus.ACTIVE,
            stream_id="ingest-studio-002",
            title="Stream Quality Degraded",
            description="Packet loss above 1.5% for Studio A Return",
            first_seen=now - timedelta(minutes=11),
            last_seen=now - timedelta(seconds=35),
        ),
        Alarm(
            id="alarm-1002",
            severity=AlarmSeverity.CRITICAL,
            status=AlarmStatus.ACTIVE,
            stream_id="ingest-backup-004",
            title="Backup Stream Offline",
            description="Backup Program Feed is offline",
            first_seen=now - timedelta(minutes=17, seconds=34),
            last_seen=now - timedelta(minutes=1),
        ),
        Alarm(
            id="alarm-1003",
            severity=AlarmSeverity.WARNING,
            status=AlarmStatus.ACKNOWLEDGED,
            stream_id=None,
            title="Network Utilization High",
            description="NIC transmit utilization above 75%",
            first_seen=now - timedelta(minutes=29),
            last_seen=now - timedelta(minutes=5),
            acknowledged_by="noc.alon",
            acknowledged_at=now - timedelta(minutes=5),
        ),
        Alarm(
            id="alarm-1004",
            severity=AlarmSeverity.INFO,
            status=AlarmStatus.RESOLVED,
            stream_id=None,
            title="Preview Service Recovered",
            description="Preview thumbnail generation recovered",
            first_seen=now - timedelta(hours=2, minutes=4),
            last_seen=now - timedelta(hours=1, minutes=48),
            resolved_at=now - timedelta(hours=1, minutes=48),
        ),
    ]


def get_system() -> SystemResponse:
    now = _now()
    settings = get_settings()
    host = HostHealth(
        hostname="srs-monitor-node-01",
        status=ServiceState.DEGRADED,
        uptime_seconds=113420,
        cpu_percent=42.7,
        load_average=[1.42, 1.18, 0.93],
        memory=CapacityMetric(used=8.6, total=16.0, unit="GB"),
        disk=CapacityMetric(used=184.0, total=512.0, unit="GB"),
        network=[
            NetworkInterface(name="eth0", rx_mbps=184.2, tx_mbps=412.8, errors_per_minute=0),
            NetworkInterface(name="eth1", rx_mbps=22.4, tx_mbps=95.1, errors_per_minute=2),
        ],
    )
    srs = SrsHealth(
        api_url=settings.srs_api_url,
        status=ServiceState.HEALTHY,
        version="5.0.213",
        connections=2778,
        publishers=4,
        subscribers=2774,
        recv_kbps=20500,
        send_kbps=845000,
    )
    services = [
        ServiceHealth(
            name="monitor-backend",
            status=ServiceState.HEALTHY,
            replicas=1,
            healthy_replicas=1,
            latency_ms=12,
            last_check_at=now - timedelta(seconds=8),
        ),
        ServiceHealth(
            name="preview-service",
            status=ServiceState.HEALTHY,
            replicas=1,
            healthy_replicas=1,
            latency_ms=24,
            last_check_at=now - timedelta(seconds=9),
        ),
        ServiceHealth(
            name="srs",
            status=ServiceState.HEALTHY,
            replicas=1,
            healthy_replicas=1,
            latency_ms=18,
            last_check_at=now - timedelta(seconds=6),
        ),
    ]
    return SystemResponse(generated_at=now, host=host, srs=srs, services=services)


def get_stream_summary(streams: list[IngestStream] | None = None) -> StreamSummary:
    streams = streams or get_streams()
    return StreamSummary(
        total=len(streams),
        online=sum(stream.status == StreamStatus.ONLINE for stream in streams),
        degraded=sum(stream.status == StreamStatus.DEGRADED for stream in streams),
        offline=sum(stream.status == StreamStatus.OFFLINE for stream in streams),
        total_viewers=sum(stream.viewers_current for stream in streams),
        ingest_bitrate_kbps=sum(stream.metrics.bitrate_kbps for stream in streams),
    )


def get_streams_response() -> StreamsResponse:
    streams = get_streams()
    return StreamsResponse(generated_at=_now(), total=len(streams), streams=streams)


def get_clients_response() -> ClientsResponse:
    clients = get_clients()
    return ClientsResponse(
        generated_at=_now(),
        total=len(clients),
        connected=sum(client.status == ClientStatus.CONNECTED for client in clients),
        buffering=sum(client.status == ClientStatus.BUFFERING for client in clients),
        clients=clients,
    )


def get_alarms_response() -> AlarmsResponse:
    alarms = get_alarms()
    return AlarmsResponse(
        generated_at=_now(),
        total=len(alarms),
        active=sum(alarm.status == AlarmStatus.ACTIVE for alarm in alarms),
        critical=sum(alarm.severity == AlarmSeverity.CRITICAL for alarm in alarms),
        alarms=alarms,
    )


def get_dashboard() -> DashboardResponse:
    settings = get_settings()
    streams = get_streams()
    active_alarms = [alarm for alarm in get_alarms() if alarm.status == AlarmStatus.ACTIVE]
    system = get_system()
    top_streams = sorted(streams, key=lambda stream: stream.viewers_current, reverse=True)[:3]
    return DashboardResponse(
        generated_at=_now(),
        mock_mode=settings.mock_mode,
        stream_summary=get_stream_summary(streams),
        host=system.host,
        srs=system.srs,
        top_streams=top_streams,
        active_alarms=active_alarms,
    )
