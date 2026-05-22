export type HealthState = "healthy" | "warning" | "critical" | "unknown" | "srs_unreachable";

export interface Alarm {
  id: string;
  severity: "info" | "warning" | "critical";
  status: "active" | "acknowledged" | "resolved";
  stream_id: string | null;
  title: string;
  description: string;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface AlarmsResponse {
  generated_at: string;
  total: number;
  active: number;
  critical: number;
  alarms: Alarm[];
}

export interface Stream {
  id: string;
  name: string;
  protocol: string;
  status: string;
  app: string;
  stream_key: string;
  source_ip: string;
  uptime_seconds: number;
  viewers_current: number;
  outputs?: Record<string, string>;
  debug?: Record<string, unknown>;
  metrics: {
    bitrate_kbps: number | null;
    fps: number | null;
    scan_type: "progressive" | "interlaced" | "unknown";
    resolution: string;
    video_codec: string;
    audio_codec?: string;
  };
}

export interface StreamsResponse {
  generated_at: string;
  total: number;
  streams: Stream[];
}

export interface Client {
  id: string;
  stream_id: string;
  stream_name: string;
  protocol: string;
  status: string;
  ip: string;
  connected_at: string | null;
  duration_seconds: number | null;
  bitrate_kbps: number | null;
  user_agent?: string;
  player?: string;
}

export interface ClientsResponse {
  generated_at: string;
  total: number;
  connected: number;
  buffering: number;
  clients: Client[];
}

export interface ExpectedStream {
  id: number;
  stream_id: string;
  friendly_name: string;
  umd: string;
  customer_or_event: string;
  expected_protocol: string;
  expected_source_ip_or_cidr: string;
  expected_min_bitrate: number | null;
  expected_max_bitrate: number | null;
  expected_resolution: string;
  expected_fps: number | null;
  encryption_required: boolean;
  auth_required: boolean;
  token_required: boolean;
  auth_mode: "token_and_ip" | "ip_only" | "disabled";
  allowed_publish_cidrs: string;
  allowed_play_cidrs: string;
  srt_encryption_required: boolean;
  srt_pbkeylen: number;
  srt_passphrase?: string | null;
  has_srt_passphrase?: boolean;
  priority: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ExpectedStreamsResponse {
  total: number;
  streams: ExpectedStream[];
}

export interface GlobalSrtSecurityConfig {
  srt_encryption_required: boolean;
  srt_pbkeylen: number;
  has_srt_passphrase: boolean;
  srt_passphrase?: string | null;
  updated_at?: string | null;
}

export interface SystemResponse {
  generated_at: string;
  host: {
    hostname: string;
    status: HealthState;
    uptime_seconds: number;
    cpu_percent: number;
    memory: { used: number; total: number; unit: string };
    disk: { used: number; total: number; unit: string };
    network: Array<{ name: string; rx_mbps: number; tx_mbps: number; errors_per_minute: number }>;
    debug?: Record<string, unknown>;
  };
  srs: {
    api_url: string;
    status: HealthState;
    version: string;
    uptime_seconds: number;
    connections: number;
    publishers: number;
    subscribers: number;
    recv_kbps: number;
    send_kbps: number;
    debug?: Record<string, unknown>;
  };
  services: Array<{
    name: string;
    status: HealthState;
    replicas: number;
    healthy_replicas: number;
    latency_ms: number;
    last_check_at: string;
  }>;
}

export interface DashboardResponse {
  generated_at: string;
  stream_summary: {
    total: number;
    online: number;
    degraded: number;
    offline: number;
    total_viewers: number;
    ingest_bitrate_kbps: number;
  };
  top_streams: Stream[];
}

export type MultiviewLayoutType =
  | "1x1"
  | "2x2"
  | "3x3"
  | "4x4"
  | "5x5"
  | "1+5"
  | "1+7"
  | "2_large_8_small"
  | "custom";

export interface MultiviewTile {
  id: string;
  position: number;
  row: number;
  column: number;
  row_span: number;
  column_span: number;
  assigned_stream_id: string | null;
  muted: boolean;
  show_overlay: boolean;
}

export interface MultiviewLayout {
  id: number;
  name: string;
  type: MultiviewLayoutType;
  is_default: boolean;
  tiles: MultiviewTile[];
  created_at: string;
  updated_at: string;
}

export interface MultiviewLayoutsResponse {
  total: number;
  layouts: MultiviewLayout[];
}

export interface PreviewResolveResponse {
  stream_id: string;
  state: "available" | "preview_started" | "preview_unavailable";
  source: "native_webrtc" | "native_hls" | "native_http_flv" | "preview_hls" | "none";
  playback_url: string | null;
  reason: string | null;
  debug?: Record<string, unknown> | null;
}

export interface PreviewStatusResponse {
  reachable: boolean;
  previews: Array<Record<string, unknown>>;
  error: string | null;
}

export interface LiveBundle {
  generated_at: string;
  dashboard: DashboardResponse;
  streams: StreamsResponse;
  alarms: AlarmsResponse;
  preview: PreviewStatusResponse;
}

export interface StreamNoteEvent {
  id: number;
  note: string;
  author: string;
  updated_at: string;
}

export interface StreamNotesResponse {
  stream_id: string;
  note: string;
  updated_at: string | null;
  history: StreamNoteEvent[];
}
