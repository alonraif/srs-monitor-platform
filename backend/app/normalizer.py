from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import Any

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
    HealthResponse,
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
from .publisher_ip_cache import resolve_publish_ip
from .srs_client import SrsApiSnapshot


JsonObject = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _as_dict(value: Any) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unknown(value: Any) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value)


def _infer_scan_type(raw: JsonObject, video: JsonObject) -> str:
    # SRS does not expose a single canonical scan-type field across endpoints.
    # We infer from best-effort metadata names seen in ffprobe-like sidecars or
    # custom SRS extensions and default to unknown when absent.
    text = " ".join(
        _unknown(value).lower()
        for value in (
            video.get("scan_type"),
            video.get("field_order"),
            video.get("interlaced"),
            raw.get("scan_type"),
            raw.get("field_order"),
            raw.get("interlaced"),
        )
    )
    if "interlaced" in text or "tt" in text or "bb" in text or "tb" in text or "bt" in text or "true" in text:
        return "interlaced"
    if "progressive" in text or "false" in text:
        return "progressive"
    return "unknown"


def _items(response: JsonObject | None, key: str) -> list[JsonObject]:
    if not response:
        return []

    # SRS v1 collection endpoints return a top-level list such as "streams" or
    # "clients". Some versions/extensions may nest resources under "data", so
    # we also check there before giving up.
    direct_items = _as_list(response.get(key))
    nested_items = _as_list(_as_dict(response.get("data")).get(key))
    return [item for item in [*direct_items, *nested_items] if isinstance(item, dict)]


def normalize_health(snapshot: SrsApiSnapshot | None = None) -> HealthResponse:
    settings = get_settings()
    health_state = ServiceState.HEALTHY
    debug: dict[str, Any] | None = None

    if snapshot is not None:
        if not snapshot.reachable:
            health_state = ServiceState.SRS_UNREACHABLE
        elif snapshot.errors:
            health_state = ServiceState.DEGRADED
        debug = {
            "srs_reachable": snapshot.reachable,
            "srs_errors": snapshot.errors,
        }

    return HealthResponse(
        status="ok",
        health_state=health_state,
        service=settings.service_name,
        version=settings.version,
        mock_mode=settings.mock_mode,
        srs_api_url=settings.srs_api_url,
        debug=debug,
    )


def normalize_streams_response(snapshot: SrsApiSnapshot) -> StreamsResponse:
    streams = normalize_streams(snapshot)
    return StreamsResponse(generated_at=_now(), total=len(streams), streams=streams)


def normalize_streams(snapshot: SrsApiSnapshot) -> list[IngestStream]:
    if not snapshot.reachable:
        return []

    stream_items = _items(snapshot.responses.get("streams"), "streams")
    if not stream_items:
        stream_items = _streams_from_vhosts(snapshot.responses.get("vhosts"))

    publisher_ip_by_cid = _publisher_ip_by_cid(snapshot.responses.get("clients"))
    publisher_alive_by_cid = _publisher_alive_seconds_by_cid(snapshot.responses.get("clients"))
    external_viewers_by_stream = _external_viewers_by_stream(snapshot.responses.get("clients"))
    return [
        _normalize_stream(item, publisher_ip_by_cid, publisher_alive_by_cid, external_viewers_by_stream)
        for item in stream_items
    ]


def _publisher_ip_by_cid(clients_response: JsonObject | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for client in _items(clients_response, "clients"):
        cid = _unknown(client.get("id"))
        ip = _unknown(client.get("ip"))
        if cid != "unknown" and ip != "unknown":
            mapping[cid] = ip
    return mapping


def _external_viewers_by_stream(clients_response: JsonObject | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for client in _items(clients_response, "clients"):
        if not _is_external_playback_client(client):
            continue
        stream_id = _unknown(client.get("stream"))
        if stream_id == "unknown":
            continue
        counts[stream_id] = counts.get(stream_id, 0) + 1
    return counts


def _is_external_playback_client(raw: JsonObject) -> bool:
    publish_flag = raw.get("publish")
    ctype = _unknown(raw.get("type")).lower()
    # SRS "type" commonly includes play/publish variants.
    is_playback = (publish_flag is False) or ("play" in ctype)
    if not is_playback:
        return False
    if _is_internal_service_client(raw):
        return False
    ip = _unknown(raw.get("ip"))
    # Keep unknown IPs out of viewer counts, but include private/LAN viewers.
    if ip == "unknown":
        return False
    return True


def _is_internal_service_client(raw: JsonObject) -> bool:
    # Exclude known internal monitoring/probe consumers so viewer metrics
    # reflect only real audience clients.
    searchable = " ".join(
        str(value).lower()
        for value in (
            raw.get("user_agent"),
            raw.get("agent"),
            raw.get("name"),
            raw.get("service"),
            raw.get("type"),
        )
        if value is not None
    )
    internal_markers = (
        "ffprobe",
        "ffmpeg",
        "libavformat",
        "lavf/",
        "preview-service",
        "multiview",
        "monitor-backend",
    )
    if any(marker in searchable for marker in internal_markers):
        return True

    # Multiviewer-internal WebRTC pulls commonly show up as rtc-play with no
    # browser page/user-agent and an internal RFC1918 source IP.
    ctype = _unknown(raw.get("type")).lower()
    page_url = str(raw.get("pageUrl") or raw.get("page_url") or "").strip()
    user_agent = str(raw.get("user_agent") or raw.get("agent") or "").strip().lower()
    ip = str(raw.get("ip") or "").strip()
    if "rtc-play" in ctype and not page_url and user_agent in {"", "unknown"} and _is_rfc1918_ip(ip):
        return True

    return False


def _is_rfc1918_ip(value: str) -> bool:
    try:
        addr = ip_address(value)
    except ValueError:
        return False
    private_ranges = (
        ip_network("10.0.0.0/8"),
        ip_network("172.16.0.0/12"),
        ip_network("192.168.0.0/16"),
    )
    return any(addr in net for net in private_ranges)


def _publisher_alive_seconds_by_cid(clients_response: JsonObject | None) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for client in _items(clients_response, "clients"):
        cid = _unknown(client.get("id"))
        if cid == "unknown":
            continue
        publish_flag = client.get("publish")
        ctype = _unknown(client.get("type")).lower()
        is_publisher = (publish_flag is True) or ("publish" in ctype)
        if not is_publisher:
            continue
        alive_seconds = _as_int(client.get("alive"))
        if alive_seconds is None:
            continue
        mapping[cid] = max(alive_seconds, 0)
    return mapping


def _streams_from_vhosts(vhosts_response: JsonObject | None) -> list[JsonObject]:
    streams: list[JsonObject] = []
    for vhost in _items(vhosts_response, "vhosts"):
        for app in _as_list(vhost.get("apps")):
            if not isinstance(app, dict):
                continue
            for stream in _as_list(app.get("streams")):
                if not isinstance(stream, dict):
                    continue
                streams.append(
                    {
                        **stream,
                        "vhost": stream.get("vhost") or vhost.get("name") or vhost.get("id"),
                        "app": stream.get("app") or app.get("name") or app.get("id"),
                    }
                )
    return streams


def _normalize_stream(
    raw: JsonObject,
    publisher_ip_by_cid: dict[str, str],
    publisher_alive_by_cid: dict[str, int],
    external_viewers_by_stream: dict[str, int],
) -> IngestStream:
    now = _now()
    app = _unknown(raw.get("app"))
    stream_name = _unknown(raw.get("name") or raw.get("stream"))
    vhost = _unknown(raw.get("vhost"))
    stream_id = _unknown(raw.get("id") or f"{vhost}/{app}/{stream_name}")
    publish = _as_dict(raw.get("publish"))

    # SRS stream records usually expose publisher state under publish.active.
    # When that field is missing, the collection itself is treated as an active
    # stream snapshot and marked online.
    publish_active = publish.get("active")
    status = StreamStatus.ONLINE if publish_active is not False else StreamStatus.OFFLINE

    source_cid = _unknown(publish.get("cid"))
    uptime_seconds = publisher_alive_by_cid.get(source_cid, _extract_uptime_seconds(raw, now))
    started_at = now - timedelta(seconds=uptime_seconds) if uptime_seconds else None
    kbps = _as_dict(raw.get("kbps"))
    video = _as_dict(raw.get("video"))
    audio = _as_dict(raw.get("audio"))
    width = _as_int(video.get("width"))
    height = _as_int(video.get("height"))
    resolution = f"{width}x{height}" if width and height else "unknown"

    # SRS does not consistently identify the ingest protocol in /streams. We
    # infer it from textual URL/type fields and default to RTMP, the common SRS
    # publisher protocol for these records.
    protocol = _infer_protocol(raw, default=StreamProtocol.RTMP)

    viewers = external_viewers_by_stream.get(stream_id, 0)
    recv_kbps = _as_int(kbps.get("recv_30s") or kbps.get("recv") or raw.get("recv_kbps"))

    source_ip = _unknown(raw.get("ip") or publish.get("ip") or raw.get("remote_ip"))
    if source_ip == "unknown" and source_cid != "unknown":
        # Some SRS builds only expose publisher cid on /streams and actual IP on
        # /clients. We join by cid when available.
        source_ip = publisher_ip_by_cid.get(source_cid, "unknown")
    if source_ip == "unknown":
        cached_ip = resolve_publish_ip(app=app, stream=stream_name, stream_id=stream_id)
        if cached_ip:
            source_ip = cached_ip

    fps = _as_float(video.get("fps") or raw.get("fps"))
    if fps is None:
        frames = _as_int(raw.get("frames"))
        # SRS may omit fps in /streams; estimate from total frames / uptime.
        if frames is not None and frames > 0 and uptime_seconds > 0:
            fps = round(frames / uptime_seconds, 2)

    return IngestStream(
        id=stream_id,
        name=stream_name,
        protocol=protocol,
        status=status,
        app=app,
        stream_key=stream_name,
        source_ip=source_ip,
        ingest_region="unknown",
        origin_node=_unknown(raw.get("server") or raw.get("node")),
        started_at=started_at,
        last_seen_at=now,
        uptime_seconds=uptime_seconds,
        viewers_current=viewers,
        viewers_peak_1h=viewers,
        metrics=StreamMetrics(
            bitrate_kbps=recv_kbps,
            fps=fps,
            scan_type=_infer_scan_type(raw, video),
            resolution=resolution,
            video_codec=_unknown(video.get("codec") or raw.get("vcodec")),
            audio_codec=_unknown(audio.get("codec") or raw.get("acodec")),
            latency_ms=None,
            packet_loss_percent=None,
            jitter_ms=None,
            keyframe_interval_seconds=None,
        ),
        outputs={},
        tags=[f"vhost:{vhost}"],
        debug={"srs_stream": raw},
    )


def _extract_uptime_seconds(raw: JsonObject, now: datetime) -> int:
    live_ms = _as_int(raw.get("live_ms"))
    if live_ms is not None:
        # In some SRS builds, live_ms is stream start timestamp (epoch ms);
        # in others it is elapsed duration in ms.
        epoch_now_ms = int(datetime.now(UTC).timestamp() * 1000)
        if live_ms > 946684800000:  # >= 2000-01-01 epoch ms
            # Some SRS responses report live_ms close to "current time" rather
            # than start-time or elapsed duration. Treat near-now as unknown.
            if abs(epoch_now_ms - live_ms) <= 10_000:
                return 0
        if 0 < live_ms <= epoch_now_ms and live_ms > 946684800000:
            return max(int((epoch_now_ms - live_ms) / 1000), 0)
        return max(int(live_ms / 1000), 0)

    alive_seconds = _as_int(raw.get("alive"))
    if alive_seconds is not None:
        return max(alive_seconds, 0)

    duration_ms = _as_int(raw.get("duration_ms"))
    if duration_ms is not None:
        return max(int(duration_ms / 1000), 0)

    return 0


def normalize_clients_response(snapshot: SrsApiSnapshot) -> ClientsResponse:
    clients = normalize_clients(snapshot)
    return ClientsResponse(
        generated_at=_now(),
        total=len(clients),
        connected=sum(client.status == ClientStatus.CONNECTED for client in clients),
        buffering=sum(client.status == ClientStatus.BUFFERING for client in clients),
        clients=clients,
    )


def normalize_clients(snapshot: SrsApiSnapshot) -> list[Client]:
    if not snapshot.reachable:
        return []

    client_items = _items(snapshot.responses.get("clients"), "clients")
    stream_names = {
        stream.id: stream.name
        for stream in normalize_streams(snapshot)
    }
    normalized: list[Client] = []
    for item in client_items:
        if not _is_external_playback_client(item):
            continue
        normalized.append(_normalize_client(item, stream_names))
    return normalized


def _normalize_client(raw: JsonObject, stream_names: dict[str, str]) -> Client:
    now = _now()
    stream_id = _unknown(raw.get("stream") or raw.get("stream_id") or raw.get("url"))
    alive_seconds = _as_int(raw.get("alive"))
    kbps = _as_dict(raw.get("kbps"))

    # SRS client objects use "type" values such as play/publish variants. They
    # are not a full player taxonomy, so protocol/player are best-effort labels.
    protocol = _infer_protocol(raw, default=StreamProtocol.RTMP)
    status = ClientStatus.DISCONNECTED if raw.get("alive") == 0 else ClientStatus.CONNECTED

    bitrate = _as_int(kbps.get("send_30s") or kbps.get("recv_30s") or raw.get("send_kbps"))
    return Client(
        id=_unknown(raw.get("id")),
        stream_id=stream_id,
        stream_name=stream_names.get(stream_id, stream_id),
        protocol=protocol,
        status=status,
        ip=_unknown(raw.get("ip")),
        country="unknown",
        city="unknown",
        user_agent=_unknown(raw.get("user_agent") or raw.get("agent")),
        player=_unknown(raw.get("type")),
        connected_at=now - timedelta(seconds=alive_seconds) if alive_seconds else None,
        duration_seconds=alive_seconds,
        bitrate_kbps=bitrate,
        buffer_health_seconds=None,
        dropped_frames=None,
        debug={"srs_client": raw},
    )


def normalize_alarms_response(snapshot: SrsApiSnapshot) -> AlarmsResponse:
    alarms = normalize_alarms(snapshot)
    return AlarmsResponse(
        generated_at=_now(),
        total=len(alarms),
        active=sum(alarm.status == AlarmStatus.ACTIVE for alarm in alarms),
        critical=sum(alarm.severity == AlarmSeverity.CRITICAL for alarm in alarms),
        alarms=alarms,
    )


def normalize_alarms(snapshot: SrsApiSnapshot) -> list[Alarm]:
    now = _now()
    if not snapshot.reachable:
        return [
            Alarm(
                id="srs-unreachable",
                severity=AlarmSeverity.CRITICAL,
                status=AlarmStatus.ACTIVE,
                stream_id=None,
                title="SRS API Unreachable",
                description=f"SRS HTTP API is unreachable at {snapshot.base_url}",
                first_seen=now,
                last_seen=now,
            )
        ]

    if not snapshot.errors:
        return []

    return [
        Alarm(
            id=f"srs-api-partial-{name}",
            severity=AlarmSeverity.WARNING,
            status=AlarmStatus.ACTIVE,
            stream_id=None,
            title="SRS API Partial Failure",
            description=f"SRS API endpoint '{name}' could not be polled",
            first_seen=now,
            last_seen=now,
        )
        for name in sorted(snapshot.errors)
    ]


def normalize_system(snapshot: SrsApiSnapshot) -> SystemResponse:
    now = _now()
    srs = normalize_srs_health(snapshot)
    host = normalize_host_health(snapshot)
    return SystemResponse(
        generated_at=now,
        host=host,
        srs=srs,
        services=[
            ServiceHealth(
                name="monitor-backend",
                status=ServiceState.HEALTHY,
                replicas=1,
                healthy_replicas=1,
                latency_ms=0,
                last_check_at=now,
            ),
            ServiceHealth(
                name="srs",
                status=srs.status,
                replicas=1,
                healthy_replicas=1 if srs.status == ServiceState.HEALTHY else 0,
                latency_ms=0,
                last_check_at=now,
            ),
        ],
    )


def normalize_srs_health(snapshot: SrsApiSnapshot) -> SrsHealth:
    summary = snapshot.responses.get("summaries")
    data = _as_dict(summary.get("data")) if summary else {}
    self_data = _as_dict(data.get("self"))
    system_data = _as_dict(data.get("system"))
    streams = normalize_streams(snapshot)
    clients = normalize_clients(snapshot)

    if not snapshot.reachable:
        return SrsHealth(
            api_url=snapshot.base_url,
            status=ServiceState.SRS_UNREACHABLE,
            version="unknown",
            uptime_seconds=0,
            connections=0,
            publishers=0,
            subscribers=0,
            recv_kbps=0,
            send_kbps=0,
            debug={"srs_errors": snapshot.errors},
        )

    # SRS summaries provide sampled byte counters, not always explicit kbps
    # fields. We keep the raw values in debug and expose a best-effort kbps
    # number when the fields are available.
    recv_kbps = _bytes_to_kbps(system_data.get("srs_recv_bytes"))
    send_kbps = _bytes_to_kbps(system_data.get("srs_send_bytes"))
    publishers = sum(stream.status == StreamStatus.ONLINE for stream in streams)
    connection_count = _as_int(system_data.get("conn_srs")) or len(clients)
    status = ServiceState.DEGRADED if snapshot.errors else ServiceState.HEALTHY

    srs_uptime_seconds = _as_int(self_data.get("srs_uptime"))
    if srs_uptime_seconds is None:
        srs_uptime_seconds = _as_int(system_data.get("uptime"))

    return SrsHealth(
        api_url=snapshot.base_url,
        status=status,
        version=_unknown(self_data.get("version")),
        uptime_seconds=max(srs_uptime_seconds or 0, 0),
        connections=connection_count,
        publishers=publishers,
        subscribers=max(connection_count - publishers, len(clients)),
        recv_kbps=recv_kbps,
        send_kbps=send_kbps,
        debug={
            "srs_summaries": summary,
            "srs_errors": snapshot.errors,
        },
    )


def normalize_host_health(snapshot: SrsApiSnapshot) -> HostHealth:
    summary = snapshot.responses.get("summaries")
    data = _as_dict(summary.get("data")) if summary else {}
    self_data = _as_dict(data.get("self"))
    system_data = _as_dict(data.get("system"))

    if not snapshot.reachable:
        return HostHealth(
            hostname="unknown",
            status=ServiceState.SRS_UNREACHABLE,
            uptime_seconds=0,
            cpu_percent=0,
            load_average=[],
            memory=CapacityMetric(used=0, total=100, unit="percent"),
            disk=CapacityMetric(used=0, total=100, unit="percent"),
            network=[],
            debug={"srs_errors": snapshot.errors},
        )

    memory_percent = _as_float(system_data.get("mem_ram_percent")) or 0
    disk_busy_percent = _as_float(system_data.get("disk_busy_percent")) or 0
    cpu_percent = _as_float(system_data.get("cpu_percent")) or 0
    status = ServiceState.DEGRADED if cpu_percent >= 90 or memory_percent >= 90 else ServiceState.HEALTHY

    return HostHealth(
        hostname=_unknown(self_data.get("server") or snapshot.responses.get("summaries", {}).get("server")),
        status=status,
        uptime_seconds=_as_int(system_data.get("uptime")) or 0,
        cpu_percent=cpu_percent,
        load_average=[
            value
            for value in [
                _as_float(system_data.get("load_1m")),
                _as_float(system_data.get("load_5m")),
                _as_float(system_data.get("load_15m")),
            ]
            if value is not None
        ],
        memory=CapacityMetric(used=memory_percent, total=100, unit="percent"),
        disk=CapacityMetric(used=disk_busy_percent, total=100, unit="percent"),
        network=[
            NetworkInterface(
                name="srs",
                rx_mbps=_bytes_to_mbps(system_data.get("net_recvi_bytes")),
                tx_mbps=_bytes_to_mbps(system_data.get("net_sendi_bytes")),
                errors_per_minute=0,
            )
        ],
        debug={"srs_summaries": summary},
    )


def normalize_dashboard(snapshot: SrsApiSnapshot) -> DashboardResponse:
    settings = get_settings()
    streams = normalize_streams(snapshot)
    alarms = normalize_alarms(snapshot)
    system = normalize_system(snapshot)
    top_streams = sorted(streams, key=lambda stream: stream.viewers_current, reverse=True)[:3]
    return DashboardResponse(
        generated_at=_now(),
        mock_mode=settings.mock_mode,
        stream_summary=normalize_stream_summary(streams),
        host=system.host,
        srs=system.srs,
        top_streams=top_streams,
        active_alarms=[alarm for alarm in alarms if alarm.status == AlarmStatus.ACTIVE],
    )


def normalize_stream_summary(streams: list[IngestStream]) -> StreamSummary:
    return StreamSummary(
        total=len(streams),
        online=sum(stream.status == StreamStatus.ONLINE for stream in streams),
        degraded=sum(stream.status == StreamStatus.DEGRADED for stream in streams),
        offline=sum(stream.status == StreamStatus.OFFLINE for stream in streams),
        total_viewers=sum(stream.viewers_current for stream in streams),
        ingest_bitrate_kbps=sum(stream.metrics.bitrate_kbps or 0 for stream in streams),
    )


def _infer_protocol(raw: JsonObject, default: StreamProtocol) -> StreamProtocol:
    text = " ".join(
        _unknown(raw.get(key)).lower()
        for key in ("protocol", "type", "url", "tcUrl", "pageUrl", "stream", "name")
    )
    if "srt" in text:
        return StreamProtocol.SRT
    if "webrtc" in text or "rtc" in text:
        return StreamProtocol.WEBRTC
    if "hls" in text or ".m3u8" in text:
        return StreamProtocol.HLS
    if "rtmp" in text:
        return StreamProtocol.RTMP
    return default


def _bytes_to_kbps(value: Any) -> int:
    byte_count = _as_int(value)
    if byte_count is None:
        return 0
    return int(byte_count * 8 / 1000)


def _bytes_to_mbps(value: Any) -> float:
    byte_count = _as_float(value)
    if byte_count is None:
        return 0
    return round(byte_count * 8 / 1_000_000, 3)
