from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class StreamProtocol(StrEnum):
    SRT = "SRT"
    RTMP = "RTMP"
    HLS = "HLS"
    WEBRTC = "WebRTC"


class StreamStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class ClientStatus(StrEnum):
    CONNECTED = "connected"
    BUFFERING = "buffering"
    DISCONNECTED = "disconnected"


class AlarmSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ServiceState(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"
    DOWN = "down"
    SRS_UNREACHABLE = "srs_unreachable"


class StreamMetrics(BaseModel):
    bitrate_kbps: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, ge=0)
    scan_type: Literal["progressive", "interlaced", "unknown"] = "unknown"
    resolution: str
    video_codec: str
    audio_codec: str
    audio_channels: int | None = Field(default=None, ge=1, le=32)
    latency_ms: int | None = Field(default=None, ge=0)
    packet_loss_percent: float | None = Field(default=None, ge=0)
    jitter_ms: int | None = Field(default=None, ge=0)
    keyframe_interval_seconds: float | None = Field(default=None, ge=0)


class IngestStream(BaseModel):
    id: str
    name: str
    protocol: StreamProtocol
    status: StreamStatus
    app: str
    stream_key: str
    source_ip: str
    ingest_region: str
    origin_node: str
    started_at: datetime | None
    last_seen_at: datetime
    uptime_seconds: int = Field(ge=0)
    viewers_current: int = Field(ge=0)
    viewers_peak_1h: int = Field(ge=0)
    metrics: StreamMetrics
    outputs: dict[str, str]
    tags: list[str] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class StreamSummary(BaseModel):
    total: int = Field(ge=0)
    online: int = Field(ge=0)
    degraded: int = Field(ge=0)
    offline: int = Field(ge=0)
    total_viewers: int = Field(ge=0)
    ingest_bitrate_kbps: int = Field(ge=0)


class StreamsResponse(BaseModel):
    generated_at: datetime
    total: int = Field(ge=0)
    streams: list[IngestStream]


class Client(BaseModel):
    id: str
    stream_id: str
    stream_name: str
    protocol: StreamProtocol
    status: ClientStatus
    ip: str
    country: str
    city: str
    user_agent: str
    player: str
    connected_at: datetime | None
    duration_seconds: int | None = Field(default=None, ge=0)
    bitrate_kbps: int | None = Field(default=None, ge=0)
    buffer_health_seconds: float | None = Field(default=None, ge=0)
    dropped_frames: int | None = Field(default=None, ge=0)
    debug: dict[str, Any] | None = None


class ClientsResponse(BaseModel):
    generated_at: datetime
    total: int = Field(ge=0)
    connected: int = Field(ge=0)
    buffering: int = Field(ge=0)
    clients: list[Client]


class Alarm(BaseModel):
    id: str
    severity: AlarmSeverity
    status: AlarmStatus
    stream_id: str | None = None
    title: str
    description: str
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class AlarmsResponse(BaseModel):
    generated_at: datetime
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    critical: int = Field(ge=0)
    alarms: list[Alarm]


class CapacityMetric(BaseModel):
    used: float = Field(ge=0)
    total: float = Field(gt=0)
    unit: Literal["percent", "GB", "Mbps"]


class NetworkInterface(BaseModel):
    name: str
    rx_mbps: float = Field(ge=0)
    tx_mbps: float = Field(ge=0)
    errors_per_minute: int = Field(ge=0)


class HostHealth(BaseModel):
    hostname: str
    status: ServiceState
    uptime_seconds: int = Field(ge=0)
    cpu_percent: float = Field(ge=0, le=100)
    load_average: list[float]
    memory: CapacityMetric
    disk: CapacityMetric
    network: list[NetworkInterface]
    debug: dict[str, Any] | None = None


class SrsHealth(BaseModel):
    api_url: str
    status: ServiceState
    version: str
    uptime_seconds: int = Field(ge=0)
    connections: int = Field(ge=0)
    publishers: int = Field(ge=0)
    subscribers: int = Field(ge=0)
    recv_kbps: int = Field(ge=0)
    send_kbps: int = Field(ge=0)
    debug: dict[str, Any] | None = None


class ServiceHealth(BaseModel):
    name: str
    status: ServiceState
    replicas: int = Field(ge=0)
    healthy_replicas: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    last_check_at: datetime


class SystemResponse(BaseModel):
    generated_at: datetime
    host: HostHealth
    srs: SrsHealth
    services: list[ServiceHealth]


class DashboardResponse(BaseModel):
    generated_at: datetime
    mock_mode: bool
    stream_summary: StreamSummary
    host: HostHealth
    srs: SrsHealth
    top_streams: list[IngestStream]
    active_alarms: list[Alarm]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    health_state: ServiceState
    service: str
    version: str
    mock_mode: bool
    srs_api_url: str
    debug: dict[str, Any] | None = None


class ExpectedStreamBase(BaseModel):
    stream_id: str = Field(min_length=1, max_length=120)
    friendly_name: str = Field(min_length=1, max_length=200)
    umd: str = Field(default="unknown", max_length=120)
    customer_or_event: str = Field(default="unknown", max_length=200)
    expected_protocol: str = Field(default="unknown", max_length=40)
    expected_source_ip_or_cidr: str = Field(default="unknown", max_length=120)
    expected_min_bitrate: int | None = Field(default=None, ge=0)
    expected_max_bitrate: int | None = Field(default=None, ge=0)
    expected_resolution: str = Field(default="unknown", max_length=40)
    expected_fps: float | None = Field(default=None, ge=0)
    encryption_required: bool = False
    auth_required: bool = True
    token_required: bool = True
    auth_mode: Literal["token_and_ip", "ip_only", "disabled"] = "token_and_ip"
    allowed_publish_cidrs: str = Field(default="", max_length=1000)
    allowed_play_cidrs: str = Field(default="", max_length=1000)
    srt_encryption_required: bool = False
    srt_pbkeylen: int = Field(default=16)
    srt_passphrase: str | None = Field(default=None, max_length=200)
    priority: int = Field(default=3, ge=1, le=5)
    notes: str = Field(default="", max_length=2000)


class ExpectedStreamCreate(ExpectedStreamBase):
    pass


class ExpectedStreamUpdate(BaseModel):
    friendly_name: str = Field(min_length=1, max_length=200)
    umd: str = Field(default="unknown", max_length=120)
    customer_or_event: str = Field(default="unknown", max_length=200)
    expected_protocol: str = Field(default="unknown", max_length=40)
    expected_source_ip_or_cidr: str = Field(default="unknown", max_length=120)
    expected_min_bitrate: int | None = Field(default=None, ge=0)
    expected_max_bitrate: int | None = Field(default=None, ge=0)
    expected_resolution: str = Field(default="unknown", max_length=40)
    expected_fps: float | None = Field(default=None, ge=0)
    encryption_required: bool = False
    auth_required: bool = True
    token_required: bool = True
    auth_mode: Literal["token_and_ip", "ip_only", "disabled"] = "token_and_ip"
    allowed_publish_cidrs: str = Field(default="", max_length=1000)
    allowed_play_cidrs: str = Field(default="", max_length=1000)
    srt_encryption_required: bool = False
    srt_pbkeylen: int = Field(default=16)
    srt_passphrase: str | None = Field(default=None, max_length=200)
    priority: int = Field(default=3, ge=1, le=5)
    notes: str = Field(default="", max_length=2000)


class ExpectedStreamRecord(ExpectedStreamBase):
    id: int
    has_srt_passphrase: bool = False
    created_at: datetime
    updated_at: datetime


class StreamNoteUpdate(BaseModel):
    note: str = Field(default="", max_length=4000)
    author: str = Field(default="operator", max_length=120)


class StreamNoteEvent(BaseModel):
    id: int
    note: str
    author: str
    updated_at: datetime


class StreamNotesResponse(BaseModel):
    stream_id: str
    note: str
    updated_at: datetime | None = None
    history: list[StreamNoteEvent] = Field(default_factory=list)


class ExpectedStreamsResponse(BaseModel):
    total: int = Field(ge=0)
    streams: list[ExpectedStreamRecord]


class GlobalSrtSecurityConfig(BaseModel):
    srt_encryption_required: bool = False
    srt_pbkeylen: int = Field(default=16)
    has_srt_passphrase: bool = False
    srt_passphrase: str | None = Field(default=None, max_length=200)
    updated_at: datetime | None = None


class GlobalSrtSecurityUpdate(BaseModel):
    srt_encryption_required: bool = False
    srt_pbkeylen: int = Field(default=16)
    srt_passphrase: str | None = Field(default=None, max_length=200)


class MultiviewLayoutType(StrEnum):
    GRID_1X1 = "1x1"
    GRID_2X2 = "2x2"
    GRID_3X3 = "3x3"
    GRID_4X4 = "4x4"
    GRID_5X5 = "5x5"
    ONE_PLUS_FIVE = "1+5"
    ONE_PLUS_SEVEN = "1+7"
    TWO_LARGE_EIGHT_SMALL = "2_large_8_small"
    CUSTOM = "custom"


class MultiviewTile(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    position: int = Field(ge=0)
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    assigned_stream_id: str | None = Field(default=None, max_length=120)
    muted: bool = False
    show_overlay: bool = True


class MultiviewLayoutBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: MultiviewLayoutType
    is_default: bool = False
    tiles: list[MultiviewTile] = Field(default_factory=list)


class MultiviewLayoutCreate(MultiviewLayoutBase):
    pass


class MultiviewLayoutUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: MultiviewLayoutType
    is_default: bool = False
    tiles: list[MultiviewTile] = Field(default_factory=list)


class MultiviewLayoutRecord(MultiviewLayoutBase):
    id: int
    created_at: datetime
    updated_at: datetime


class MultiviewLayoutsResponse(BaseModel):
    total: int = Field(ge=0)
    layouts: list[MultiviewLayoutRecord]
