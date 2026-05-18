import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Hls from "hls.js";
import flvjs from "flv.js";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "./api";
import { EmptyState, ErrorState, LoadingState } from "./components";
import { useAlarmFeed, useAutoRefresh, useLiveBundle } from "./hooks";
import type {
  ExpectedStream,
  MultiviewLayout,
  MultiviewLayoutType,
  MultiviewTile,
  PreviewResolveResponse,
  Stream,
  SystemResponse
} from "./types";

function streamMatchTokens(stream: Stream): Set<string> {
  const tokens = new Set<string>();
  const id = String(stream.id || "").trim();
  const key = String(stream.stream_key || "").trim();
  const app = String(stream.app || "").trim();
  if (id) tokens.add(id);
  if (key) tokens.add(key);
  if (app && key) tokens.add(`${app}/${key}`);
  const idParts = id.split("/").filter(Boolean);
  if (idParts.length >= 1) {
    tokens.add(idParts[idParts.length - 1]);
  }
  if (idParts.length >= 2) {
    tokens.add(`${idParts[idParts.length - 2]}/${idParts[idParts.length - 1]}`);
  }
  return tokens;
}

function alarmMatchesStream(alarmStreamId: string, stream: Stream): boolean {
  const alarmId = String(alarmStreamId || "").trim().toLowerCase();
  if (!alarmId) return false;
  const tokens = Array.from(streamMatchTokens(stream)).map((v) => v.toLowerCase());
  if (tokens.includes(alarmId)) return true;
  for (const token of tokens) {
    if (alarmId.endsWith(`/${token}`)) return true;
    if (token.endsWith(`/${alarmId}`)) return true;
  }
  return false;
}

function resolveExpectedForStream(stream: Stream, expectedItems: ExpectedStream[]): ExpectedStream | undefined {
  const tokens = streamMatchTokens(stream);
  return expectedItems.find((item) => tokens.has(String(item.stream_id || "").trim()));
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function buildVlcUrl(stream: Stream): string {
  const host = window.location.hostname;
  const appKey = sanitizeSrtPath(`${stream.app}/${stream.stream_key}`);
  const proto = String(stream.protocol || "").toLowerCase();
  const base = resolveSrsHttpBaseUrl(host);
  const rtmpPort = (import.meta.env.VITE_SRS_RTMP_PORT as string | undefined) || "1935";
  const srtPort = (import.meta.env.VITE_SRS_SRT_PORT as string | undefined) || "10080";

  const flvUrl = `${base.replace(/\/$/, "")}/${appKey}.flv`;
  const hlsUrl = `${base.replace(/\/$/, "")}/${appKey}.m3u8`;
  const rtmpUrl = `rtmp://${host}:${rtmpPort}/${appKey}`;
  const srtUrl = `srt://${host}:${srtPort}?streamid=#!::r=${appKey},m=request`;

  const outputs = stream.outputs;
  const byProtocol =
    proto === "srt" ? [outputs?.srt, srtUrl, outputs?.rtmp, rtmpUrl, outputs?.flv, outputs?.httpflv, flvUrl, outputs?.hls, hlsUrl] :
    proto === "rtmp" ? [outputs?.rtmp, rtmpUrl, outputs?.srt, srtUrl, outputs?.flv, outputs?.httpflv, flvUrl, outputs?.hls, hlsUrl] :
    proto === "hls" ? [outputs?.hls, hlsUrl, outputs?.flv, outputs?.httpflv, flvUrl, outputs?.rtmp, rtmpUrl, outputs?.srt, srtUrl] :
    [outputs?.flv, outputs?.httpflv, flvUrl, outputs?.hls, hlsUrl, outputs?.rtmp, rtmpUrl, outputs?.srt, srtUrl];
  for (const candidate of byProtocol) {
    const normalized = normalizePlaybackUrl(candidate);
    if (normalized) return normalized;
  }
  return flvUrl;
}

function publicHost(): string {
  return window.location.hostname || "localhost";
}

function frontendEnv(name: string, fallback: string): string {
  const value = import.meta.env[name] as string | undefined;
  return value && value.trim() ? value.trim() : fallback;
}

function resolveBackendUrlForDisplay(host: string): string {
  const fallback = `${window.location.protocol}//${host}:8000`;
  const configured = frontendEnv("VITE_BACKEND_API_URL", fallback).trim();
  try {
    const parsed = new URL(configured, fallback);
    if (!parsed.hostname) {
      return fallback;
    }
    const isLocalhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    const isRemoteBrowser = !["localhost", "127.0.0.1"].includes(host);
    if (isLocalhost && isRemoteBrowser) {
      parsed.hostname = host;
      return parsed.toString().replace(/\/$/, "");
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
}

function resolveSrsHttpBaseUrl(host: string): string {
  const fallback = `${window.location.protocol}//${host}:8080`;
  const configured = frontendEnv("VITE_SRS_PUBLIC_HTTP_BASE_URL", fallback).trim();
  try {
    const parsed = new URL(configured, fallback);
    if (!parsed.hostname) {
      return fallback;
    }
    const isLocalhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    const isRemoteBrowser = !["localhost", "127.0.0.1"].includes(host);
    if (isLocalhost && isRemoteBrowser) {
      parsed.hostname = host;
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return fallback;
  }
}

function normalizePlaybackUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  const sanitized = trimmed.replace(/:(\d+)\}\?/g, ":$1?");
  const host = window.location.hostname;
  const base = `${window.location.protocol}//${host}`;
  try {
    const parsed = new URL(sanitized, base);
    const isLocalhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    const isRemoteBrowser = !["localhost", "127.0.0.1"].includes(host);
    if (isLocalhost && isRemoteBrowser) {
      parsed.hostname = host;
    }
    return parsed.toString();
  } catch {
    return sanitized;
  }
}

function sanitizeSrtPath(value: string): string {
  return value.replace(/,m=[a-z_]+$/i, "").trim();
}

function resolveSrsRtcApiBase(rawUrl: string): string | null {
  const configured = (import.meta.env.VITE_SRS_WEBRTC_API_BASE_URL as string | undefined)?.trim();
  if (configured) {
    try {
      return new URL(configured).toString().replace(/\/$/, "");
    } catch {
      return null;
    }
  }
  try {
    const parsed = new URL(rawUrl.replace(/^webrtc:\/\//i, "http://"));
    const apiProtocol = window.location.protocol === "https:" ? "https:" : "http:";
    const apiHost = parsed.hostname || window.location.hostname;
    const apiPort = (import.meta.env.VITE_SRS_API_PORT as string | undefined) || "1985";
    return `${apiProtocol}//${apiHost}:${apiPort}`;
  } catch {
    return null;
  }
}

function normalizeWebRtcStreamUrl(rawUrl: string): string | null {
  const value = (rawUrl || "").trim();
  if (!value) return null;
  if (value.startsWith("webrtc://")) return value;
  try {
    const parsed = new URL(value);
    const proto = parsed.protocol.toLowerCase();
    if (proto === "http:" || proto === "https:") {
      return `webrtc://${parsed.host}${parsed.pathname}`;
    }
  } catch {
    return null;
  }
  return null;
}

function toFlvVariant(url: string): string | null {
  const value = (url || "").trim();
  if (!value) return null;
  if (value.includes(".flv")) return value;
  if (!value.includes(".m3u8")) return null;
  return value.replace(/\.m3u8(\?.*)?$/i, ".flv$1");
}

function formatFps(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "unknown";
  const nearestInt = Math.round(value);
  if (Math.abs(value - nearestInt) <= 0.15) return String(nearestInt);
  return value.toFixed(1);
}

function playbackSourceLabel(source: PreviewResolveResponse["source"] | null | undefined): string {
  if (source === "native_webrtc") return "WebRTC";
  if (source === "native_hls" || source === "preview_hls") return "HLS";
  if (source === "native_http_flv") return "FLV";
  return "Unknown";
}

function formatHms(value: number | null | undefined): string {
  const total = Math.max(Math.floor(value ?? 0), 0);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function metricSeverity(value: number): "healthy" | "warning" | "critical" {
  if (value >= 95) return "critical";
  if (value >= 80) return "warning";
  return "healthy";
}

function explainOverallStatus(system: SystemResponse): string {
  if (system.host.status === "healthy") return "All backend host checks are within normal range.";
  if (system.host.status === "unknown") return "Backend health details are currently unavailable.";
  if (system.host.status === "srs_unreachable") return "SRS API is unreachable.";

  const reasons: string[] = [];
  const cpuSeverity = metricSeverity(system.host.cpu_percent);
  const memorySeverity = metricSeverity(system.host.memory.used);
  const diskSeverity = metricSeverity(system.host.disk.used);

  if (cpuSeverity !== "healthy") reasons.push(`CPU ${system.host.cpu_percent.toFixed(1)}%`);
  if (memorySeverity !== "healthy") reasons.push(`Memory ${system.host.memory.used.toFixed(1)}%`);
  if (diskSeverity !== "healthy") reasons.push(`Disk ${system.host.disk.used.toFixed(1)}%`);

  if (reasons.length > 0) return `Triggered by: ${reasons.join(", ")}.`;
  return "At least one backend health check is degraded.";
}

async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to legacy copy
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    textarea.remove();
  }
  return copied;
}

function BitrateChart({ points }: { points: Array<{ ts: number; bitrate: number }> }) {
  if (points.length < 2) {
    return <div className="state empty">Collecting bitrate samples...</div>;
  }
  const width = 900;
  const height = 220;
  const padL = 64;
  const padR = 16;
  const padT = 14;
  const padB = 36;
  const minTs = points[0].ts;
  const maxTs = points[points.length - 1].ts;
  const maxBitrate = Math.max(...points.map((point) => point.bitrate), 1);
  const minBitrate = 0;
  const ySpan = Math.max(maxBitrate - minBitrate, 1);
  const xSpan = Math.max(maxTs - minTs, 1);
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;
  const toX = (ts: number) => padL + ((ts - minTs) / xSpan) * chartW;
  const toY = (bitrate: number) => padT + (1 - (bitrate - minBitrate) / ySpan) * chartH;
  const path = points
    .map((point, idx) => `${idx === 0 ? "M" : "L"}${toX(point.ts).toFixed(2)} ${toY(point.bitrate).toFixed(2)}`)
    .join(" ");
  const last = points[points.length - 1];
  const yTicks = 4;
  const xTicks = 5;
  const fmtTime = (ts: number) =>
    new Date(ts).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => minBitrate + ((yTicks - i) / yTicks) * ySpan);
  const xTickVals = Array.from({ length: xTicks + 1 }, (_, i) => minTs + (i / xTicks) * xSpan);

  return (
    <div className="bitrate-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="bitrate-chart" role="img" aria-label="Bitrate over time">
        {yTickVals.map((v, i) => {
          const y = toY(v);
          return (
            <g key={`y-${i}`}>
              <line x1={padL} y1={y} x2={width - padR} y2={y} className="chart-grid" />
              <text x={padL - 8} y={y + 4} textAnchor="end" className="chart-label">{Math.round(v)} kbps</text>
            </g>
          );
        })}
        {xTickVals.map((v, i) => {
          const x = toX(v);
          return (
            <g key={`x-${i}`}>
              <line x1={x} y1={padT} x2={x} y2={height - padB} className="chart-grid" />
              <text x={x} y={height - 10} textAnchor="middle" className="chart-label">{fmtTime(v)}</text>
            </g>
          );
        })}
        <line x1={padL} y1={height - padB} x2={width - padR} y2={height - padB} className="chart-axis" />
        <line x1={padL} y1={padT} x2={padL} y2={height - padB} className="chart-axis" />
        <path d={path} className="chart-line" />
        <circle cx={toX(last.ts)} cy={toY(last.bitrate)} r="3" className="chart-dot" />
      </svg>
      <div className="bitrate-chart-meta">
        <span>Current: {last.bitrate} kbps</span>
        <span>Min: {Math.round(minBitrate)} kbps</span>
        <span>Max: {Math.round(maxBitrate)} kbps</span>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const liveLoader = useCallback(
    () => Promise.all([api.getDashboard(), api.getStreams(), api.getAlarms()]),
    []
  );
  const mergeLive = useCallback(
    (
      current: [Awaited<ReturnType<typeof api.getDashboard>>, Awaited<ReturnType<typeof api.getStreams>>, Awaited<ReturnType<typeof api.getAlarms>>] | null,
      live: { dashboard: Awaited<ReturnType<typeof api.getDashboard>>; streams: Awaited<ReturnType<typeof api.getStreams>>; alarms: Awaited<ReturnType<typeof api.getAlarms>> }
    ) => [live.dashboard, live.streams, live.alarms] as const,
    []
  );
  const [copiedUrlStreamId, setCopiedUrlStreamId] = useState<string | null>(null);
  const live = useLiveBundle(liveLoader, mergeLive, 1000);
  const systemFeed = useAutoRefresh(api.getSystem, 1000);
  if (live.loading || systemFeed.loading) return <LoadingState />;
  if (live.error || !live.data) return <ErrorState error={live.error || "No data"} />;
  if (systemFeed.error || !systemFeed.data) return <ErrorState error={systemFeed.error || "No system data"} />;
  const [dashboard, streams, alarms] = live.data;
  const system = systemFeed.data;
  const activeAlarms = alarms.alarms.filter((alarm) => alarm.status !== "resolved");
  const overallStatusReason = explainOverallStatus(system);

  const viewers = streams.streams.reduce((sum, stream) => sum + stream.viewers_current, 0);
  const inboundBitrateMbps =
    streams.streams.reduce((sum, stream) => sum + (stream.metrics.bitrate_kbps ?? 0), 0) / 1000;
  const outboundBitrateMbps =
    streams.streams.reduce(
      (sum, stream) => sum + ((stream.metrics.bitrate_kbps ?? 0) * stream.viewers_current),
      0
    ) / 1000;

  const mostViewedStreams = [...streams.streams]
    .sort((a, b) => {
      const viewerDelta = b.viewers_current - a.viewers_current;
      if (viewerDelta !== 0) return viewerDelta;
      return (b.metrics.bitrate_kbps ?? 0) - (a.metrics.bitrate_kbps ?? 0);
    })
    ;

  const recentEvents = [...activeAlarms]
    .sort((a, b) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime())
    .slice(0, 6);

  const healthClass = (state: string) => {
    if (state === "online") return "health health-green";
    if (state === "offline") return "health health-red";
    if (state === "degraded") return "health health-yellow";
    if (state === "healthy") return "health health-green";
    if (state === "warning") return "health health-yellow";
    if (state === "critical" || state === "srs_unreachable") return "health health-red";
    return "health";
  };

  const copyToClipboard = async (text: string, streamId?: string) => {
    const copied = await copyText(text);
    if (copied && streamId) {
      setCopiedUrlStreamId(streamId);
      window.setTimeout(() => {
        setCopiedUrlStreamId((current) => (current === streamId ? null : current));
      }, 1500);
    }
  };

  return (
    <section className="dashboard-layout">
      <div className="panel">
        <h2>System Health</h2>
        <div className="cards-grid cards-lg">
          <article className="metric-card">
            <div className="metric-head">
              <div className="metric-title">Overall</div>
              <div className={healthClass(system.host.status)}>{system.host.status}</div>
            </div>
            <div className="metric-value">monitor-backend</div>
            <div className="metric-title">Host: {system.host.hostname}</div>
            <div className="metric-reason">{overallStatusReason}</div>
          </article>
          <article className="metric-card">
            <div className="metric-head">
              <div className="metric-title">SRS</div>
          <div className={healthClass(system.srs.status)}>{system.srs.status}</div>
            </div>
            <div className="metric-value">v{system.srs.version}</div>
          </article>
          <article className="metric-card">
            <div className="metric-head">
              <div className="metric-title">Active Alarms</div>
              <div className={healthClass(activeAlarms.filter((a) => a.severity === "critical").length > 0 ? "critical" : activeAlarms.length > 0 ? "warning" : "healthy")}>
                {activeAlarms.length}
              </div>
            </div>
            <div className="metric-value">{activeAlarms.filter((a) => a.severity === "critical").length} critical</div>
          </article>
        </div>
      </div>

      <div className="panel">
        <h2>Core Metrics</h2>
        <div className="cards-grid cards-sm">
          <article className="metric-card"><div className="metric-title">Active Ingest Streams</div><div className="metric-value">{dashboard.stream_summary.online}</div></article>
          <article className="metric-card"><div className="metric-title">Active Playback Sessions</div><div className="metric-value">{viewers}</div></article>
          <article className="metric-card"><div className="metric-title">Inbound Bitrate</div><div className="metric-value">{inboundBitrateMbps.toFixed(2)} Mbps</div></article>
          <article className="metric-card"><div className="metric-title">Outbound Bitrate</div><div className="metric-value">{outboundBitrateMbps.toFixed(2)} Mbps</div></article>
          <article className="metric-card"><div className="metric-title">CPU Usage</div><div className="metric-value">{system.host.cpu_percent.toFixed(1)}%</div></article>
          <article className="metric-card"><div className="metric-title">Memory Usage</div><div className="metric-value">{system.host.memory.used.toFixed(1)}%</div></article>
          <article className="metric-card"><div className="metric-title">SRS Uptime</div><div className="metric-value">{Math.floor(system.host.uptime_seconds / 60)} min</div></article>
          <article className="metric-card"><div className="metric-title">Backend Uptime</div><div className="metric-value">{Math.floor(system.host.uptime_seconds / 60)} min</div></article>
        </div>
      </div>

      <div className="panel">
        <h2>Active Alarms</h2>
        <table className="table compact">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Status</th>
              <th>Title</th>
              <th>Stream</th>
              <th>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {activeAlarms.slice(0, 8).map((alarm) => (
              <tr key={alarm.id}>
                <td><span className={healthClass(alarm.severity === "critical" ? "critical" : alarm.severity === "warning" ? "warning" : "healthy")}>{alarm.severity}</span></td>
                <td>{alarm.status}</td>
                <td>{alarm.title}</td>
                <td>{alarm.stream_id || "-"}</td>
                <td>{new Date(alarm.last_seen).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Most Viewed Streams</h2>
        <div className="table-scroll top5-window">
          <table className="table compact">
            <thead>
              <tr>
                <th>Stream</th>
                <th>Status</th>
                <th>Bitrate</th>
                <th>Viewers</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {mostViewedStreams.map((stream) => (
                <tr key={stream.id}>
                  <td>{stream.name}</td>
                  <td><span className={healthClass(stream.status)}>{stream.status}</span></td>
                  <td>{stream.metrics.bitrate_kbps ?? "unknown"} kbps</td>
                  <td>{stream.viewers_current}</td>
                  <td>
                    <div className="vlc-cell">
                      <button className="btn-xs" onClick={() => void copyToClipboard(buildVlcUrl(stream), stream.id)}>
                        {copiedUrlStreamId === stream.id ? "Copied!" : "Copy URL"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h2>Recent Events</h2>
        <ul className="events-list">
          {recentEvents.map((alarm) => (
            <li key={`${alarm.id}-${alarm.last_seen}`} className="event-row">
              <span className={healthClass(alarm.severity === "critical" ? "critical" : alarm.severity === "warning" ? "warning" : "healthy")}>
                {alarm.severity}
              </span>
              <span className="event-title">{alarm.title}</span>
              <span className="event-time">{new Date(alarm.last_seen).toLocaleTimeString()}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function StreamsPage() {
  const navigate = useNavigate();
  const loader = useCallback(
    () => Promise.all([api.getStreams(), api.getExpectedStreams()]),
    []
  );
  const { data, error, loading } = useAutoRefresh(loader, 1000);
  const [search, setSearch] = useState("");
  const [protocolFilter, setProtocolFilter] = useState("all");
  const [healthFilter, setHealthFilter] = useState("all");
  const [sortKey, setSortKey] = useState("health");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [copiedStreamId, setCopiedStreamId] = useState<string | null>(null);
  const [showExpectedModal, setShowExpectedModal] = useState(false);
  const [expectedDraft, setExpectedDraft] = useState<Omit<ExpectedStream, "id" | "created_at" | "updated_at"> | null>(null);
  const [expectedActionError, setExpectedActionError] = useState<string | null>(null);

  const copyStreamUrl = async (stream: Stream) => {
    const copied = await copyText(buildVlcUrl(stream));
    if (copied) {
      setCopiedStreamId(stream.id);
      window.setTimeout(() => {
        setCopiedStreamId((current) => (current === stream.id ? null : current));
      }, 1400);
    }
  };

  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState error={error || "No data"} />;
  const [streamsData, expectedData] = data;
  if (streamsData.streams.length === 0) return <EmptyState message="No ingest streams available." />;

  const rows = streamsData.streams.map((stream) => {
    const expected = resolveExpectedForStream(stream, expectedData.streams);
    const health = stream.status === "online" ? "green" : stream.status === "degraded" ? "yellow" : "red";
    const inputBitrate = stream.metrics.bitrate_kbps ?? 0;
    const outputBitrate = stream.viewers_current * Math.max(Math.floor((inputBitrate || 0) * 0.35), 200);
    const mode =
      stream.protocol.toLowerCase() === "srt"
        ? "listener"
        : "-";
    const encryption =
      stream.protocol.toLowerCase() === "srt" ? "encrypted" : stream.protocol.toLowerCase() === "rtmp" ? "no-passphrase" : "unknown";
    const codec = `${stream.metrics.video_codec || "unknown"} / ${stream.metrics.audio_codec || "unknown"}`;
    return {
      stream,
      expected,
      health,
      appStream: sanitizeSrtPath(`${stream.app}/${stream.stream_key}`),
      mode,
      inputBitrate,
      outputBitrate,
      codec,
      uptime: `${Math.floor(stream.uptime_seconds / 3600)}h ${Math.floor((stream.uptime_seconds % 3600) / 60)}m`,
      encryption
    };
  });

  const protocols = ["all", ...Array.from(new Set(rows.map((r) => r.stream.protocol))).sort()];

  const filtered = rows
    .filter((row) => {
      const q = search.trim().toLowerCase();
      if (!q) return true;
      return (
        row.stream.id.toLowerCase().includes(q) ||
        row.stream.name.toLowerCase().includes(q) ||
        row.stream.source_ip.toLowerCase().includes(q) ||
        (row.expected?.umd || "").toLowerCase().includes(q)
      );
    })
    .filter((row) => (protocolFilter === "all" ? true : row.stream.protocol === protocolFilter))
    .filter((row) => {
      if (healthFilter === "all") return true;
      return row.health === healthFilter;
    })
    .sort((a, b) => {
      const mult = sortDir === "asc" ? 1 : -1;
      const rankHealth = (value: string) => (value === "green" ? 0 : value === "yellow" ? 1 : 2);
      const comparable = (row: (typeof rows)[number], key: string): string | number => {
        switch (key) {
          case "health":
            return rankHealth(row.health);
          case "name":
            return row.stream.name;
          case "umd":
            return row.expected?.umd || "unknown";
          case "protocol":
            return row.stream.protocol;
          case "app_stream":
            return row.appStream;
          case "source_ip":
            return row.stream.source_ip;
          case "mode":
            return row.mode;
          case "input":
            return row.inputBitrate;
          case "output":
            return row.outputBitrate;
          case "codec":
            return row.codec;
          case "resolution":
            return row.stream.metrics.resolution;
          case "fps":
            return row.stream.metrics.fps ?? -1;
          case "scan":
            return row.stream.metrics.scan_type ?? "unknown";
          case "uptime":
            return row.stream.uptime_seconds;
          case "encryption":
            return row.encryption;
          case "viewers":
            return row.stream.viewers_current;
          default:
            return row.stream.name;
        }
      };
      const av = comparable(a, sortKey);
      const bv = comparable(b, sortKey);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * mult;
      return String(av).localeCompare(String(bv)) * mult;
    });

  const setSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortMark = (key: string) => (sortKey !== key ? "↕" : sortDir === "asc" ? "↑" : "↓");
  const resolutionOptions = [
    "1920x1080",
    "1280x720",
    "3840x2160",
    "4096x2160",
    "1440x1080",
    "720x576",
    "720x480",
    "unknown",
  ];
  const fpsOptions = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];

  function openAddExpected(stream: Stream, expected?: ExpectedStream) {
    if (expected) return;
    setExpectedActionError(null);
    setExpectedDraft({
      stream_id: sanitizeSrtPath(stream.stream_key || stream.id),
      friendly_name: stream.name && stream.name !== "unknown" ? stream.name : stream.stream_key,
      umd: "",
      customer_or_event: "",
      expected_protocol: stream.protocol,
      expected_source_ip_or_cidr: stream.source_ip && stream.source_ip !== "unknown" ? stream.source_ip : "",
      expected_min_bitrate: stream.metrics.bitrate_kbps ? Math.max(Math.floor(stream.metrics.bitrate_kbps * 0.8), 0) : null,
      expected_max_bitrate: stream.metrics.bitrate_kbps ? Math.ceil(stream.metrics.bitrate_kbps * 1.2) : null,
      expected_resolution: stream.metrics.resolution && stream.metrics.resolution !== "unknown" ? stream.metrics.resolution : "1920x1080",
      expected_fps: stream.metrics.fps ?? null,
      encryption_required: stream.protocol === "SRT",
      priority: 3,
      notes: "",
    });
    setShowExpectedModal(true);
  }

  async function submitAddExpected() {
    if (!expectedDraft) return;
    setExpectedActionError(null);
    try {
      await api.createExpectedStream(expectedDraft);
      setShowExpectedModal(false);
      setExpectedDraft(null);
    } catch (err) {
      setExpectedActionError(err instanceof Error ? err.message : "Failed to add expected stream");
    }
  }

  return (
    <section className="panel">
      <h2>Streams</h2>
      <div className="table-toolbar">
        <input
          placeholder="Search stream, UMD, source IP"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={protocolFilter} onChange={(e) => setProtocolFilter(e.target.value)}>
          {protocols.map((value) => (
            <option key={value} value={value}>
              {value === "all" ? "All protocols" : value}
            </option>
          ))}
        </select>
        <select value={healthFilter} onChange={(e) => setHealthFilter(e.target.value)}>
          <option value="all">All health</option>
          <option value="green">Healthy</option>
          <option value="yellow">Warning</option>
          <option value="red">Critical</option>
        </select>
      </div>
      <table className="table compact streams-table">
        <thead>
          <tr>
            <th onClick={() => setSort("health")} className="sortable-col">Health <span>{sortMark("health")}</span></th>
            <th onClick={() => setSort("name")} className="sortable-col">Stream name <span>{sortMark("name")}</span></th>
            <th onClick={() => setSort("umd")} className="sortable-col">UMD <span>{sortMark("umd")}</span></th>
            <th onClick={() => setSort("protocol")} className="sortable-col">Protocol <span>{sortMark("protocol")}</span></th>
            <th>App/stream key</th>
            <th>Source IP</th>
            <th>Input bitrate</th>
            <th>Output bitrate</th>
            <th>Codec</th>
            <th>Resolution</th>
            <th>FPS</th>
            <th>Scan</th>
            <th onClick={() => setSort("uptime")} className="sortable-col">Uptime <span>{sortMark("uptime")}</span></th>
            <th onClick={() => setSort("encryption")} className="sortable-col">Encryption <span>{sortMark("encryption")}</span></th>
            <th onClick={() => setSort("viewers")} className="sortable-col">Viewers <span>{sortMark("viewers")}</span></th>
            <th>Expected</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((row) => (
            <tr key={row.stream.id} className="clickable" onClick={() => navigate(`/streams/${row.stream.id}`)}>
              <td><span className={`health health-${row.health === "green" ? "green" : row.health === "yellow" ? "yellow" : "red"}`}>{row.stream.status}</span></td>
              <td>{row.stream.name}</td>
              <td>{row.expected?.umd && row.expected.umd !== "unknown" ? row.expected.umd : "-"}</td>
              <td>{row.stream.protocol}</td>
              <td>
                <span className="app-stream-wrap">
                  <button
                    className="app-stream-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      void copyStreamUrl(row.stream);
                    }}
                  >
                    {row.appStream}
                  </button>
                  <span className={`copied-pill ${copiedStreamId === row.stream.id ? "visible" : ""}`}>Copied</span>
                </span>
              </td>
              <td>{row.stream.source_ip}</td>
              <td>{row.inputBitrate} kbps</td>
              <td>{row.outputBitrate} kbps</td>
              <td>{row.codec}</td>
              <td>{row.stream.metrics.resolution}</td>
              <td>{formatFps(row.stream.metrics.fps)}</td>
              <td>{row.stream.metrics.scan_type ?? "unknown"}</td>
              <td>{row.uptime}</td>
              <td>{row.encryption}</td>
              <td>{row.stream.viewers_current}</td>
              <td>
                {row.expected ? (
                  <span className="health health-green">Expected</span>
                ) : (
                  <button
                    className="btn-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      openAddExpected(row.stream, row.expected);
                    }}
                  >
                    Add to expected
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {showExpectedModal && expectedDraft ? (
        <div className="modal-backdrop" onClick={() => setShowExpectedModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="panel-head">
              <h2>Add Expected Stream</h2>
              <button className="btn-icon" onClick={() => setShowExpectedModal(false)} title="Close">x</button>
            </div>
            {expectedActionError ? <ErrorState error={expectedActionError} /> : null}
            <div className="expected-form-grid">
              <div className="field">
                <div className="field-label">Stream ID</div>
                <input value={expectedDraft.stream_id} onChange={(e) => setExpectedDraft({ ...expectedDraft, stream_id: e.target.value })} />
              </div>
              <div className="field">
                <div className="field-label">Friendly Name</div>
                <input value={expectedDraft.friendly_name} onChange={(e) => setExpectedDraft({ ...expectedDraft, friendly_name: e.target.value })} />
              </div>
              <div className="field">
                <div className="field-label">UMD</div>
                <input value={expectedDraft.umd} onChange={(e) => setExpectedDraft({ ...expectedDraft, umd: e.target.value })} />
              </div>
              <div className="field">
                <div className="field-label">Customer / Event</div>
                <input value={expectedDraft.customer_or_event} onChange={(e) => setExpectedDraft({ ...expectedDraft, customer_or_event: e.target.value })} />
              </div>
              <div className="field">
                <div className="field-label">Expected Protocol</div>
                <select value={expectedDraft.expected_protocol} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_protocol: e.target.value })}>
                  <option value="SRT">SRT</option>
                  <option value="RTMP">RTMP</option>
                  <option value="HLS">HLS</option>
                  <option value="WebRTC">WebRTC</option>
                  <option value="unknown">unknown</option>
                </select>
              </div>
              <div className="field">
                <div className="field-label">Expected Source IP / CIDR</div>
                <input value={expectedDraft.expected_source_ip_or_cidr} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_source_ip_or_cidr: e.target.value })} />
              </div>
              <div className="field">
                <div className="field-label">Min Bitrate (kbps)</div>
                <input type="number" value={expectedDraft.expected_min_bitrate ?? ""} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_min_bitrate: e.target.value ? Number(e.target.value) : null })} />
              </div>
              <div className="field">
                <div className="field-label">Max Bitrate (kbps)</div>
                <input type="number" value={expectedDraft.expected_max_bitrate ?? ""} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_max_bitrate: e.target.value ? Number(e.target.value) : null })} />
              </div>
              <div className="field">
                <div className="field-label">Expected Resolution</div>
                <select value={expectedDraft.expected_resolution} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_resolution: e.target.value })}>
                  {resolutionOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </div>
              <div className="field">
                <div className="field-label">Expected FPS</div>
                <select value={expectedDraft.expected_fps == null ? "" : String(expectedDraft.expected_fps)} onChange={(e) => setExpectedDraft({ ...expectedDraft, expected_fps: e.target.value ? Number(e.target.value) : null })}>
                  {fpsOptions.map((option) => <option key={option} value={String(option)}>{option}</option>)}
                  <option value="">unknown</option>
                </select>
              </div>
              <div className="field">
                <div className="field-label">Encryption Requirement</div>
                <label className="checkbox-line">
                  <input type="checkbox" checked={expectedDraft.encryption_required} onChange={(e) => setExpectedDraft({ ...expectedDraft, encryption_required: e.target.checked })} />
                  Encryption/passphrase required
                </label>
              </div>
              <div className="expected-actions">
                <button onClick={() => void submitAddExpected()}>Add to list</button>
                <button onClick={() => setShowExpectedModal(false)}>Cancel</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function StreamDetailPage() {
  const params = useParams<{ id: string }>();
  const streamId = params.id || "";
  const [copiedKey, setCopiedKey] = useState(false);
  const [noteDraft, setNoteDraft] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [noteMessage, setNoteMessage] = useState<string | null>(null);
  const [noteUpdated, setNoteUpdated] = useState(false);
  const [bitratePoints, setBitratePoints] = useState<Array<{ ts: number; bitrate: number }>>([]);
  const [bitrateWindowMs, setBitrateWindowMs] = useState<number>(5 * 60 * 1000);
  const currentBitrateRef = useRef(0);
  const loader = useCallback(
    () => Promise.all([api.getStream(streamId), api.getClients(), api.getAlarms(), api.getExpectedStreams(), api.getStreamNotes(streamId)]),
    [streamId]
  );
  const { data, error, loading } = useAutoRefresh(loader, 1000);
  const latestNote = data?.[4]?.note ?? "";
  const currentStream = data?.[0];
  const historyKey = streamId ? `bitrate-history:${streamId}` : "";
  useEffect(() => {
    if (!historyKey) return;
    try {
      const raw = localStorage.getItem(historyKey);
      if (!raw) {
        setBitratePoints([]);
        return;
      }
      const parsed = JSON.parse(raw) as Array<{ ts: number; bitrate: number }>;
      if (!Array.isArray(parsed)) return;
      const now = Date.now();
      setBitratePoints(
        parsed
          .filter((p) => typeof p.ts === "number" && typeof p.bitrate === "number" && now - p.ts <= 12 * 60 * 60 * 1000)
          .slice(-43200)
      );
    } catch {
      setBitratePoints([]);
    }
  }, [historyKey]);
  useEffect(() => {
    setNoteDraft(latestNote);
  }, [streamId, latestNote]);
  useEffect(() => {
    const inputKbps = currentStream?.metrics.bitrate_kbps ?? 0;
    const viewers = currentStream?.viewers_current ?? 0;
    // Bitrate history represents active distribution throughput for this stream.
    // If there are no clients/viewers, keep the plotted bitrate at 0.
    currentBitrateRef.current = viewers > 0 ? inputKbps * viewers : 0;
  }, [currentStream?.id, currentStream?.metrics.bitrate_kbps, currentStream?.viewers_current]);
  useEffect(() => {
    if (!streamId) return;
    const timer = window.setInterval(() => {
      const now = Date.now();
      const bitrate = currentBitrateRef.current;
      setBitratePoints((prev) => {
        const next = [...prev, { ts: now, bitrate }];
        const bounded = next.filter((p) => now - p.ts <= 12 * 60 * 60 * 1000).slice(-43200);
        if (historyKey) {
          try {
            localStorage.setItem(historyKey, JSON.stringify(bounded));
          } catch {
            // no-op
          }
        }
        return bounded;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [streamId, historyKey]);
  const visibleBitratePoints = useMemo(() => {
    const now = Date.now();
    return bitratePoints.filter((p) => now - p.ts <= bitrateWindowMs);
  }, [bitratePoints, bitrateWindowMs]);
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState error={error || "No stream data"} />;
  const [stream, clientsResponse, alarmsResponse, expectedResponse, notesResponse] = data;
  const clients = clientsResponse.clients.filter((client) => {
    if (client.stream_id !== stream.id) return false;
    const player = String(client.player || "").toLowerCase();
    return player.includes("play");
  });
  const events = alarmsResponse.alarms
    .filter((alarm) => alarm.stream_id === stream.id)
    .sort((a, b) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime());
  const expected = resolveExpectedForStream(stream, expectedResponse.streams);

  const onCopyKey = async () => {
    const copied = await copyText(buildVlcUrl(stream));
    if (copied) {
      setCopiedKey(true);
      window.setTimeout(() => setCopiedKey(false), 1400);
    }
  };

  const onUpdateNote = async () => {
    setSavingNote(true);
    setNoteMessage(null);
    setNoteUpdated(false);
    try {
      await api.updateStreamNotes(stream.id, noteDraft);
      setNoteUpdated(true);
      window.setTimeout(() => setNoteUpdated(false), 1500);
    } catch (err) {
      setNoteMessage(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSavingNote(false);
    }
  };

  const noteEvents = notesResponse.history.map((item) => ({
    id: `note-${item.id}`,
    severity: "info" as const,
    title: "Operator note updated",
    lastSeen: item.updated_at,
    type: "note" as const
  }));
  const alarmEvents = events.map((event) => ({
    id: `${event.id}-${event.last_seen}`,
    severity: event.severity,
    title: event.title,
    lastSeen: event.last_seen,
    type: "alarm" as const
  }));
  const timelineEvents = [...alarmEvents, ...noteEvents]
    .sort((a, b) => new Date(b.lastSeen).getTime() - new Date(a.lastSeen).getTime())
    .slice(0, 40);
  return (
    <section className="grid two">
      <div className="panel">
        <h2>Ingest Details</h2>
        <div className="stats-row">
          <Stat label="Name" value={stream.name} />
          <Stat label="Health" value={stream.status} />
          <Stat label="Protocol" value={stream.protocol} />
          <div className="stat">
            <div className="stat-label">App/Key</div>
            <div className="stat-value">
              <span className="app-stream-wrap">
                <button className="app-stream-link" onClick={() => void onCopyKey()}>{`${stream.app}/${stream.stream_key}`}</button>
                <span className={`copied-pill ${copiedKey ? "visible" : ""}`}>Copied</span>
              </span>
            </div>
          </div>
          <Stat label="Source IP" value={stream.source_ip} />
          <Stat label="Input bitrate" value={`${stream.metrics.bitrate_kbps ?? "unknown"} kbps`} />
          <Stat label="Codec" value={`${stream.metrics.video_codec} / ${stream.metrics.audio_codec || "unknown"}`} />
          <Stat label="Resolution" value={stream.metrics.resolution} />
          <Stat label="FPS" value={formatFps(stream.metrics.fps)} />
          <Stat label="Scan" value={stream.metrics.scan_type ?? "unknown"} />
          <Stat label="Uptime" value={`${Math.floor(stream.uptime_seconds / 3600)}h ${Math.floor((stream.uptime_seconds % 3600) / 60)}m`} />
          <Stat label="Viewer count" value={stream.viewers_current} />
          <Stat label="UMD" value={expected?.umd && expected.umd !== "unknown" ? expected.umd : "-"} />
          <Stat label="Expected Stream" value={expected ? "Yes" : "No"} />
        </div>
      </div>
      <div className="panel">
        <h2>Distribution Clients</h2>
        <table className="table compact">
          <thead>
            <tr>
              <th>Client</th>
              <th>IP</th>
              <th>Protocol</th>
              <th>Duration</th>
              <th>Bandwidth</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => (
              <tr key={client.id}>
                <td>{client.id}</td>
                <td>{client.ip}</td>
                <td>{client.protocol}</td>
                <td>{formatHms(client.duration_seconds)}</td>
                <td>{client.bitrate_kbps ?? "unknown"} kbps</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Timeline / Events</h2>
        <ul className="events-list">
          {timelineEvents.length === 0 ? <li className="event-row"><span className="health">info</span><span className="event-title">No stream events</span><span className="event-time">-</span></li> : null}
          {timelineEvents.map((event) => (
            <li key={event.id} className="event-row">
              <span className={`health health-${event.severity === "critical" ? "red" : event.severity === "warning" ? "yellow" : "green"}`}>{event.severity}</span>
              <span className="event-title">{event.title}</span>
              <span className="event-time">{new Date(event.lastSeen).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Bitrate History</h2>
          <select
            className="input compact"
            value={String(bitrateWindowMs)}
            onChange={(e) => setBitrateWindowMs(Number(e.target.value))}
          >
            <option value={60_000}>Last 1 min</option>
            <option value={300_000}>Last 5 min</option>
            <option value={900_000}>Last 15 min</option>
            <option value={3_600_000}>Last 1 hour</option>
            <option value={43_200_000}>Last 12 hours</option>
          </select>
        </div>
        <BitrateChart points={visibleBitratePoints} />
      </div>

      <div className="panel">
        <h2>Operator Notes</h2>
        <textarea className="notes-box" value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} />
        <div className="row-actions">
          <button
            className={`update-note-btn ${noteUpdated ? "is-updated" : ""}`}
            onClick={() => void onUpdateNote()}
            disabled={savingNote}
          >
            {savingNote ? "Updating..." : noteUpdated ? "Updated" : "Update"}
          </button>
          {noteMessage ? <span className="health health-red">{noteMessage}</span> : null}
        </div>
      </div>

      <div className="panel">
        <h2>Raw SRS Data</h2>
        <details>
          <summary>Toggle raw payload</summary>
          <pre className="raw-json">{JSON.stringify(stream.debug || {}, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}

export function AlarmsPage() {
  const loader = useCallback(() => Promise.all([api.getAlarms(), api.getStreams(), api.getExpectedStreams()]), []);
  const feed = useAlarmFeed(api.getAlarms, 5000);
  const { data: streamData, error: streamError, loading: streamLoading } = useAutoRefresh(loader, 5000);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [streamFilter, setStreamFilter] = useState("all");
  const [actionError, setActionError] = useState<string | null>(null);
  if (feed.loading || streamLoading) return <LoadingState />;
  if (feed.error) return <ErrorState error={feed.error} />;
  if (streamError || !streamData || !feed.data) return <ErrorState error={streamError || "No alarm data"} />;
  const [_, streamsResponse, expectedResponse] = streamData;
  const data = feed.data;
  const streamOptionItems = streamsResponse.streams
    .map((stream) => {
      const expected = resolveExpectedForStream(stream, expectedResponse.streams);
      const preferredName =
        (expected?.friendly_name && expected.friendly_name !== "unknown" ? expected.friendly_name : null) ||
        (expected?.umd && expected.umd !== "unknown" ? expected.umd : null) ||
        (stream.name && stream.name !== "unknown" ? stream.name : null) ||
        stream.stream_key;
      return {
        value: stream.id,
        label: `${preferredName} (${stream.id})`,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));

  const byFilter = (alarm: (typeof data.active)[number]) => {
    if (severityFilter !== "all" && alarm.severity !== severityFilter) return false;
    if (streamFilter !== "all" && (alarm.stream_id || "") !== streamFilter) return false;
    return true;
  };

  const filteredActive = data.active.filter(byFilter);
  const filteredResolved = data.resolved.filter(byFilter);

  async function onAck(id: string, ack: boolean) {
    setActionError(null);
    try {
      if (ack) await api.ackAlarm(id);
      else await api.unackAlarm(id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Alarm action failed");
    }
  }

  return (
    <section className="panel">
      <h2>Alarms</h2>
      {actionError ? <ErrorState error={actionError} /> : null}
      <div className="table-toolbar">
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
          <option value="all">All severities</option>
          <option value="critical">critical</option>
          <option value="warning">warning</option>
          <option value="info">info</option>
        </select>
        <select value={streamFilter} onChange={(e) => setStreamFilter(e.target.value)}>
          <option value="all">All streams</option>
          {streamOptionItems.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>

      <h3 className="subhead">Active Alarms</h3>
      <table className="table compact">
        <thead>
          <tr>
            <th>ID</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Title</th>
            <th>Stream</th>
            <th>Last Seen</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {filteredActive.map((alarm) => (
            <tr key={alarm.id}>
              <td>{alarm.id}</td>
              <td><span className={`health health-${alarm.severity === "critical" ? "red" : alarm.severity === "warning" ? "yellow" : "green"}`}>{alarm.severity}</span></td>
              <td>{alarm.status}</td>
              <td>{alarm.title}</td>
              <td>{alarm.stream_id || "-"}</td>
              <td>{new Date(alarm.last_seen).toLocaleString()}</td>
              <td>
                {alarm.status === "acknowledged" ? (
                  <button onClick={() => void onAck(alarm.id, false)}>Unack</button>
                ) : (
                  <button onClick={() => void onAck(alarm.id, true)}>Ack</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="subhead">Resolved Alarms</h3>
      <table className="table compact">
        <thead>
          <tr>
            <th>ID</th>
            <th>Severity</th>
            <th>Title</th>
            <th>Stream</th>
            <th>Resolved At</th>
          </tr>
        </thead>
        <tbody>
          {filteredResolved.slice(0, 100).map((alarm) => (
            <tr key={`${alarm.id}-${alarm.resolved_at || alarm.last_seen}`}>
              <td>{alarm.id}</td>
              <td><span className={`health health-${alarm.severity === "critical" ? "red" : alarm.severity === "warning" ? "yellow" : "green"}`}>{alarm.severity}</span></td>
              <td>{alarm.title}</td>
              <td>{alarm.stream_id || "-"}</td>
              <td>{new Date(alarm.resolved_at || alarm.last_seen).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="subhead">Alarm History</h3>
      <ul className="events-list">
        {data.history.slice(0, 120).map((event) => (
          <li key={event.id} className="event-row">
            <span className={`health health-${event.severity === "critical" ? "red" : event.severity === "warning" ? "yellow" : "green"}`}>{event.action}</span>
            <span className="event-title">{event.title}{event.stream_id ? ` (${event.stream_id})` : ""}</span>
            <span className="event-time">{new Date(event.timestamp).toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

const defaultExpectedStream: Omit<ExpectedStream, "id" | "created_at" | "updated_at"> = {
  stream_id: "",
  friendly_name: "",
  umd: "",
  customer_or_event: "",
  expected_protocol: "SRT",
  expected_source_ip_or_cidr: "",
  expected_min_bitrate: null,
  expected_max_bitrate: null,
  expected_resolution: "1920x1080",
  expected_fps: 50,
  encryption_required: false,
  priority: 3,
  notes: ""
};

export function ExpectedStreamsPage() {
  const loader = useCallback(
    () => Promise.all([api.getExpectedStreams(), api.getStreams()]),
    []
  );
  const { data, error, loading } = useAutoRefresh(loader, 5000);
  const [form, setForm] = useState(defaultExpectedStream);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const resolutionOptions = [
    "1920x1080",
    "1280x720",
    "3840x2160",
    "4096x2160",
    "1440x1080",
    "720x576",
    "720x480",
  ];
  const fpsOptions = [23.976, 24, 25, 29.97, 30, 50, 59.94, 60];

  async function onDelete(streamId: string) {
    setActionError(null);
    try {
      await api.deleteExpectedStream(streamId);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function encryptionStatus(expectedProtocol: string, required: boolean) {
    if (expectedProtocol.toLowerCase() === "unknown") return "unknown";
    return required ? "configured" : "missing";
  }

  async function onSave() {
    setActionError(null);
    try {
      if (editingId) {
        const { stream_id: _ignored, ...payload } = form;
        await api.updateExpectedStream(editingId, payload);
      } else {
        await api.createExpectedStream(form);
      }
      setEditingId(null);
      setIsFormOpen(false);
      setForm(defaultExpectedStream);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Save failed");
    }
  }

  function onEdit(stream: ExpectedStream) {
    setEditingId(stream.stream_id);
    setIsFormOpen(true);
    const { id: _id, created_at: _created, updated_at: _updated, ...editable } = stream;
    setForm(editable);
  }

  function onCancelForm() {
    setEditingId(null);
    setIsFormOpen(false);
    setForm(defaultExpectedStream);
  }

  function onOpenCreate() {
    setActionError(null);
    setEditingId(null);
    setForm(defaultExpectedStream);
    setIsFormOpen(true);
  }

  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState error={error || "No expected streams"} />;
  const [expectedData, streamsData] = data;

  const liveByToken = new Map<string, Stream>();
  for (const stream of streamsData.streams) {
    for (const token of streamMatchTokens(stream)) {
      if (!liveByToken.has(token)) {
        liveByToken.set(token, stream);
      }
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Expected Streams</h2>
        <button className="btn-icon" onClick={onOpenCreate} title="Add expected stream">+</button>
      </div>
      {actionError ? <ErrorState error={actionError} /> : null}
      {isFormOpen ? (
      <div className="modal-backdrop" onClick={onCancelForm}>
        <div className="modal-card" onClick={(e) => e.stopPropagation()}>
          <div className="panel-head">
            <h2>{editingId ? "Edit Expected Stream" : "Add Expected Stream"}</h2>
            <button className="btn-icon" onClick={onCancelForm} title="Close">x</button>
          </div>
          <div className="expected-form-grid">
        <div className="field">
          <div className="field-label">Stream ID <span className="info-dot" title="Use stream key or app/stream key. Example: main-program-1 or live/main-program-1">i</span></div>
          <input
            placeholder="Stream ID"
            value={form.stream_id}
            disabled={Boolean(editingId)}
            onChange={(e) => setForm({ ...form, stream_id: e.target.value })}
          />
        </div>
        <div className="field">
          <div className="field-label">Friendly Name</div>
          <input
            placeholder="Friendly name"
            value={form.friendly_name}
            onChange={(e) => setForm({ ...form, friendly_name: e.target.value })}
          />
        </div>
        <div className="field">
          <div className="field-label">UMD</div>
          <input placeholder="UMD" value={form.umd} onChange={(e) => setForm({ ...form, umd: e.target.value })} />
        </div>
        <div className="field">
          <div className="field-label">Customer / Event</div>
          <input
            placeholder="Customer or event"
            value={form.customer_or_event}
            onChange={(e) => setForm({ ...form, customer_or_event: e.target.value })}
          />
        </div>
        <div className="field">
          <div className="field-label">Expected Protocol</div>
          <select
            value={form.expected_protocol}
            onChange={(e) => setForm({ ...form, expected_protocol: e.target.value })}
          >
            <option value="SRT">SRT</option>
            <option value="RTMP">RTMP</option>
            <option value="HLS">HLS</option>
            <option value="WebRTC">WebRTC</option>
            <option value="unknown">unknown</option>
          </select>
        </div>
        <div className="field">
          <div className="field-label">Expected Source IP / CIDR <span className="info-dot" title="Single IP or CIDR range. Example: 151.101.0.223 or 151.101.0.0/24">i</span></div>
          <input
            placeholder="Expected source IP or CIDR"
            value={form.expected_source_ip_or_cidr}
            onChange={(e) => setForm({ ...form, expected_source_ip_or_cidr: e.target.value })}
          />
        </div>
        <div className="field">
          <div className="field-label">Min Bitrate (kbps)</div>
          <input
            type="number"
            placeholder="min bitrate kbps"
            value={form.expected_min_bitrate ?? ""}
            onChange={(e) => setForm({ ...form, expected_min_bitrate: e.target.value ? Number(e.target.value) : null })}
          />
        </div>
        <div className="field">
          <div className="field-label">Max Bitrate (kbps)</div>
          <input
            type="number"
            placeholder="max bitrate kbps"
            value={form.expected_max_bitrate ?? ""}
            onChange={(e) => setForm({ ...form, expected_max_bitrate: e.target.value ? Number(e.target.value) : null })}
          />
        </div>
        <div className="field">
          <div className="field-label">Expected Resolution</div>
          <select
            value={form.expected_resolution}
            onChange={(e) => setForm({ ...form, expected_resolution: e.target.value })}
          >
            {resolutionOptions.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
            <option value="unknown">unknown</option>
          </select>
        </div>
        <div className="field">
          <div className="field-label">Expected FPS</div>
          <select
            value={form.expected_fps == null ? "" : String(form.expected_fps)}
            onChange={(e) => setForm({ ...form, expected_fps: e.target.value ? Number(e.target.value) : null })}
          >
            {fpsOptions.map((option) => (
              <option key={option} value={String(option)}>{option}</option>
            ))}
            <option value="">unknown</option>
          </select>
        </div>
        <div className="field">
          <div className="field-label">Encryption Requirement</div>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={form.encryption_required}
              onChange={(e) => setForm({ ...form, encryption_required: e.target.checked })}
            />
            Encryption/passphrase required
          </label>
        </div>
        <div className="expected-actions">
          <button onClick={() => void onSave()}>{editingId ? "Apply" : "Add to list"}</button>
          <button onClick={onCancelForm}>Cancel</button>
        </div>
      </div>
      </div>
      </div>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>Active</th>
            <th>Stream ID</th>
            <th>Name</th>
            <th>UMD</th>
            <th>Customer/Event</th>
            <th>Protocol</th>
            <th>Source</th>
            <th>Bitrate Range</th>
            <th>Resolution/FPS</th>
            <th>Encryption</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {expectedData.streams.map((stream) => {
            const live = liveByToken.get(stream.stream_id);
            const isActive = Boolean(live && live.status === "online");
            return (
            <tr key={stream.stream_id}>
              <td>
                <span className={`health ${isActive ? "health-green" : "health-red"}`}>
                  {isActive ? "active" : "inactive"}
                </span>
              </td>
              <td>{stream.stream_id}</td>
              <td>{stream.friendly_name || "-"}</td>
              <td>{stream.umd && stream.umd !== "unknown" ? stream.umd : "-"}</td>
              <td>{stream.customer_or_event && stream.customer_or_event !== "unknown" ? stream.customer_or_event : "-"}</td>
              <td>{stream.expected_protocol && stream.expected_protocol !== "unknown" ? stream.expected_protocol : "-"}</td>
              <td>{stream.expected_source_ip_or_cidr && stream.expected_source_ip_or_cidr !== "unknown" ? stream.expected_source_ip_or_cidr : "-"}</td>
              <td>
                {(stream.expected_min_bitrate ?? "-")} - {(stream.expected_max_bitrate ?? "-")} kbps
              </td>
              <td>
                {(stream.expected_resolution && stream.expected_resolution !== "unknown" ? stream.expected_resolution : "-")} / {stream.expected_fps ?? "-"} fps
              </td>
              <td>{encryptionStatus(stream.expected_protocol, stream.encryption_required) || "-"}</td>
              <td className="row-actions">
                <button onClick={() => onEdit(stream)}>Edit</button>
                <button onClick={() => void onDelete(stream.stream_id)}>Delete</button>
              </td>
            </tr>
          );
          })}
        </tbody>
      </table>
    </section>
  );
}

function buildTiles(type: MultiviewLayoutType): MultiviewTile[] {
  const grid = (rows: number, cols: number) => {
    const out: MultiviewTile[] = [];
    let pos = 0;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        out.push({
          id: `tile-${pos}`,
          position: pos,
          row: r,
          column: c,
          row_span: 1,
          column_span: 1,
          assigned_stream_id: null,
          muted: false,
          show_overlay: true
        });
        pos += 1;
      }
    }
    return out;
  };
  if (type === "1x1") return grid(1, 1);
  if (type === "2x2") return grid(2, 2);
  if (type === "3x3") return grid(3, 3);
  if (type === "4x4") return grid(4, 4);
  if (type === "5x5") return grid(5, 5);
  if (type === "1+5") {
    return [
      { id: "tile-main", position: 0, row: 0, column: 0, row_span: 2, column_span: 2, assigned_stream_id: null, muted: false, show_overlay: true },
      ...grid(3, 2).map((t) => ({ ...t, id: `tile-s-${t.position}`, position: t.position + 1, row: t.row, column: t.column + 2 }))
    ];
  }
  if (type === "1+7") {
    return [
      { id: "tile-main", position: 0, row: 0, column: 0, row_span: 2, column_span: 2, assigned_stream_id: null, muted: false, show_overlay: true },
      ...grid(4, 2).map((t) => ({ ...t, id: `tile-s-${t.position}`, position: t.position + 1, row: t.row, column: t.column + 2 }))
    ];
  }
  if (type === "2_large_8_small") {
    return [
      { id: "tile-l1", position: 0, row: 0, column: 0, row_span: 2, column_span: 2, assigned_stream_id: null, muted: false, show_overlay: true },
      { id: "tile-l2", position: 1, row: 0, column: 2, row_span: 2, column_span: 2, assigned_stream_id: null, muted: false, show_overlay: true },
      ...grid(2, 4).map((t) => ({ ...t, id: `tile-sm-${t.position}`, position: t.position + 2, row: t.row + 2, column: t.column }))
    ];
  }
  return grid(2, 2);
}

function buildGridTiles(rows: number, cols: number): MultiviewTile[] {
  const out: MultiviewTile[] = [];
  let pos = 0;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      out.push({
        id: `tile-${pos}`,
        position: pos,
        row: r,
        column: c,
        row_span: 1,
        column_span: 1,
        assigned_stream_id: null,
        muted: true,
        show_overlay: true,
      });
      pos += 1;
    }
  }
  return out;
}

function TilePlayer({
  playbackUrl,
  muted,
  scanType,
  protocol,
  children
}: {
  playbackUrl: string | null;
  muted: boolean;
  scanType: "progressive" | "interlaced" | "unknown";
  protocol: string | null | undefined;
  children?: ReactNode;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [boxSize, setBoxSize] = useState<{ width: number; height: number } | null>(null);
  // Only deinterlace when we are sure the feed is interlaced.
  // Treating "unknown" as interlaced is expensive in multiview and can cause stalls.
  const shouldDeinterlace = scanType === "interlaced";
  const aggressiveSrtDeinterlace = scanType === "interlaced" && String(protocol || "").toUpperCase() === "SRT";

  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    let alive = true;
    let raf = 0;
    const resize = () => {
      if (!alive) return;
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w <= 0 || h <= 0) {
        // Retry until layout has measurable size.
        raf = window.requestAnimationFrame(resize);
        return;
      }
      const target = 16 / 9;
      const current = w / h;
      if (current > target) {
        const nh = h;
        const nw = Math.floor(h * target);
        setBoxSize({ width: nw, height: nh });
      } else {
        const nw = w;
        const nh = Math.floor(w / target);
        setBoxSize({ width: nw, height: nh });
      }
    };
    resize();
    const onWindowResize = () => resize();
    window.addEventListener("resize", onWindowResize);
    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => resize());
      ro.observe(el);
    } else {
      const timer = window.setInterval(() => resize(), 500);
      return () => {
        alive = false;
        window.clearInterval(timer);
        window.removeEventListener("resize", onWindowResize);
      };
    }
    return () => {
      alive = false;
      if (raf) window.cancelAnimationFrame(raf);
      ro?.disconnect();
      window.removeEventListener("resize", onWindowResize);
    };
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !playbackUrl) return;
    let hls: { destroy: () => void } | null = null;
    let flv: { destroy: () => void; unload: () => void; detachMediaElement: () => void } | null = null;
    let pc: RTCPeerConnection | null = null;
    let onStall: (() => void) | null = null;
    let active = true;
    video.muted = muted;
    video.playsInline = true;
    video.autoplay = true;
    video.controls = false;
    const load = async () => {
      try {
        const isWebRtc = playbackUrl.startsWith("webrtc://");
        if (isWebRtc) {
          const streamUrl = normalizeWebRtcStreamUrl(playbackUrl);
          const apiBase = streamUrl ? resolveSrsRtcApiBase(streamUrl) : null;
          if (!streamUrl || !apiBase) throw new Error("invalid_webrtc_url");
          const connection = new RTCPeerConnection();
          pc = connection;
          connection.addTransceiver("audio", { direction: "recvonly" });
          connection.addTransceiver("video", { direction: "recvonly" });
          connection.ontrack = (event) => {
            const [stream] = event.streams;
            if (!stream || !active) return;
            video.srcObject = stream;
            void video.play().catch(() => undefined);
          };
          const offer = await connection.createOffer();
          await connection.setLocalDescription(offer);
          const response = await fetch(`${apiBase}/rtc/v1/play/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api: `${apiBase}/rtc/v1/play/`,
              streamurl: streamUrl,
              clientip: null,
              sdp: offer.sdp || "",
            }),
          });
          if (!response.ok) throw new Error(`webrtc_offer_failed_${response.status}`);
          const payload = (await response.json()) as { code?: number; sdp?: string };
          if (payload.code && payload.code !== 0) throw new Error(`webrtc_offer_error_${payload.code}`);
          if (!payload.sdp) throw new Error("webrtc_missing_answer");
          if (!active) return;
          await connection.setRemoteDescription({ type: "answer", sdp: payload.sdp });
        } else if (playbackUrl.includes(".m3u8")) {
          const flvVariant = toFlvVariant(playbackUrl);
          if (flvVariant && flvjs.isSupported()) {
            const player = flvjs.createPlayer(
              { type: "flv", url: flvVariant, isLive: true },
              {
                enableWorker: true,
                enableStashBuffer: true,
                stashInitialSize: 384,
                autoCleanupSourceBuffer: true,
                autoCleanupMaxBackwardDuration: 20,
                autoCleanupMinBackwardDuration: 10,
                lazyLoad: false,
              }
            );
            player.attachMediaElement(video);
            player.load();
            void Promise.resolve(player.play()).catch(() => undefined);
            flv = player;
          } else if (Hls.isSupported()) {
            const instance = new Hls({
              liveDurationInfinity: true,
              // Favor continuity in multiview over minimum latency.
              lowLatencyMode: false,
              maxBufferLength: 20,
              backBufferLength: 8,
              liveSyncDurationCount: 5,
              liveMaxLatencyDurationCount: 12,
            });
            instance.on(Hls.Events.MANIFEST_PARSED, () => {
              void video.play().catch(() => undefined);
            });
            instance.on(Hls.Events.ERROR, (_event, data) => {
              if (!active) return;
              if (data?.fatal) {
                if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                  instance.startLoad();
                  return;
                }
                if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                  instance.recoverMediaError();
                  return;
                }
                instance.destroy();
              }
            });
            onStall = () => {
              if (!active) return;
              const buffered = video.buffered;
              if (!buffered || buffered.length === 0) return;
              const end = buffered.end(buffered.length - 1);
              if (end - video.currentTime > 0.75) {
                video.currentTime = Math.max(video.currentTime, end - 0.2);
                void video.play().catch(() => undefined);
              }
            };
            video.addEventListener("stalled", onStall);
            video.addEventListener("waiting", onStall);
            instance.loadSource(playbackUrl);
            instance.attachMedia(video);
            hls = instance;
          } else {
            video.src = playbackUrl;
            await video.play().catch(() => undefined);
          }
        } else if (playbackUrl.includes(".flv")) {
          if (flvjs.isSupported()) {
            const player = flvjs.createPlayer({ type: "flv", url: playbackUrl });
            player.attachMediaElement(video);
            player.load();
            void Promise.resolve(player.play()).catch(() => undefined);
            flv = player;
          } else {
            video.src = playbackUrl;
            await video.play().catch(() => undefined);
          }
        } else {
          video.src = playbackUrl;
          await video.play().catch(() => undefined);
        }
      } catch {
        // fall through to overlay state
      }
    };
    void load();
    return () => {
      if (!active) return;
      active = false;
      if (hls) hls.destroy();
      if (flv) {
        flv.unload();
        flv.detachMediaElement();
        flv.destroy();
      }
      if (pc) {
        pc.ontrack = null;
        pc.close();
      }
      if (onStall) {
        video.removeEventListener("stalled", onStall);
        video.removeEventListener("waiting", onStall);
      }
      video.srcObject = null;
      video.removeAttribute("src");
      video.load();
    };
  }, [playbackUrl]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = muted;
  }, [muted]);

  useEffect(() => {
    if (!shouldDeinterlace) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    let rafId = 0;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;

    let bobPhase = 0;
    const draw = () => {
      if (video.videoWidth <= 0 || video.videoHeight <= 0) {
        rafId = window.requestAnimationFrame(draw);
        return;
      }

      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      }

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const px = frame.data;
      const stride = canvas.width * 4;

      if (aggressiveSrtDeinterlace) {
        // Aggressive bob deinterlace for interlaced SRT feeds:
        // preserve only one field per frame and upscale it to full frame.
        const source = new Uint8ClampedArray(px);
        const parity = bobPhase & 1;
        for (let y = 0; y < canvas.height; y += 1) {
          const srcLine = Math.min(
            canvas.height - 1,
            Math.max(0, Math.floor(y / 2) * 2 + parity)
          );
          const srcRow = srcLine * stride;
          const dstRow = y * stride;
          for (let x = 0; x < stride; x += 4) {
            px[dstRow + x] = source[srcRow + x];
            px[dstRow + x + 1] = source[srcRow + x + 1];
            px[dstRow + x + 2] = source[srcRow + x + 2];
            px[dstRow + x + 3] = source[srcRow + x + 3];
          }
        }
        bobPhase += 1;
      } else {
        for (let y = 1; y < canvas.height - 1; y += 2) {
          const row = y * stride;
          const above = (y - 1) * stride;
          const below = (y + 1) * stride;
          for (let x = 0; x < stride; x += 4) {
            px[row + x] = (px[above + x] + px[below + x]) >> 1;
            px[row + x + 1] = (px[above + x + 1] + px[below + x + 1]) >> 1;
            px[row + x + 2] = (px[above + x + 2] + px[below + x + 2]) >> 1;
          }
        }
      }

      ctx.putImageData(frame, 0, 0);
      rafId = window.requestAnimationFrame(draw);
    };

    rafId = window.requestAnimationFrame(draw);
    return () => {
      if (rafId) window.cancelAnimationFrame(rafId);
    };
  }, [shouldDeinterlace, aggressiveSrtDeinterlace, playbackUrl]);

  return (
    <div ref={frameRef} className="mv-media-frame">
      <div
        className="mv-media-box"
        style={
          boxSize
            ? { width: `${boxSize.width}px`, height: `${boxSize.height}px` }
            : { width: "100%", height: "100%" }
        }
      >
        <video ref={videoRef} className={`mv-video ${shouldDeinterlace ? "is-hidden" : ""}`} muted={muted} />
        {shouldDeinterlace ? <canvas ref={canvasRef} className="mv-video mv-canvas" /> : null}
        {children}
      </div>
    </div>
  );
}

export function MultiviewerPage() {
  const navigate = useNavigate();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const tileRefs = useRef<Record<string, HTMLElement | null>>({});
  const [selectedLayoutId, setSelectedLayoutId] = useState<number | null>(null);
  const [previewByStream, setPreviewByStream] = useState<Record<string, PreviewResolveResponse | null>>({});
  const [soloTileId, setSoloTileId] = useState<string | null>(null);
  const [soloAnimating, setSoloAnimating] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const previewRetryAtRef = useRef<Record<string, number>>({});
  const [localLayouts, setLocalLayouts] = useState<MultiviewLayout[] | null>(null);
  const [alertsDrawerOpen, setAlertsDrawerOpen] = useState(false);
  const [bootstrapDone, setBootstrapDone] = useState(false);
  const layoutStorageKey = "multiview:last-layout-id";

  const presetOptions: Array<{ key: string; label: string; rows: number; cols: number; layoutType: MultiviewLayoutType }> = [
    { key: "1x2", label: "1x2", rows: 1, cols: 2, layoutType: "custom" },
    { key: "2x2", label: "2x2", rows: 2, cols: 2, layoutType: "2x2" },
    { key: "2x3", label: "2x3", rows: 2, cols: 3, layoutType: "custom" },
    { key: "3x3", label: "3x3", rows: 3, cols: 3, layoutType: "3x3" },
    { key: "4x4", label: "4x4", rows: 4, cols: 4, layoutType: "4x4" },
  ];

  const loader = useCallback(
    () => Promise.all([api.getStreams(), api.getAlarms(), api.getMultiviewLayouts(), api.getExpectedStreams()]),
    []
  );
  const mergeLive = useCallback(
    (
      current: [Awaited<ReturnType<typeof api.getStreams>>, Awaited<ReturnType<typeof api.getAlarms>>, Awaited<ReturnType<typeof api.getMultiviewLayouts>>, Awaited<ReturnType<typeof api.getExpectedStreams>>] | null,
      live: { streams: Awaited<ReturnType<typeof api.getStreams>>; alarms: Awaited<ReturnType<typeof api.getAlarms>> }
    ) => {
      if (!current) {
        return [
          live.streams,
          live.alarms,
          { total: 0, layouts: [] },
          { total: 0, streams: [] }
        ] as const;
      }
      return [live.streams, live.alarms, current[2], current[3]] as const;
    },
    []
  );
  const live = useLiveBundle(loader, mergeLive, 4000);

  const effectiveData = live.data;
  const streams = effectiveData?.[0].streams ?? [];
  const alarms = effectiveData?.[1].alarms ?? [];
  const stickyAlarmState = useRef<Map<string, { alarm: (typeof alarms)[number]; seenAtMs: number }>>(new Map());
  const stickyAlarmHoldMs = 12_000;
  const serverLayouts = effectiveData?.[2].layouts ?? [];
  const layouts = localLayouts ?? serverLayouts;
  const expectedItems = effectiveData?.[3].streams ?? [];
  const activeAlarms = useMemo(() => {
    const nowMs = Date.now();
    const currentActive = alarms.filter((alarm) => alarm.status !== "resolved");
    for (const alarm of currentActive) {
      stickyAlarmState.current.set(alarm.id, { alarm, seenAtMs: nowMs });
    }
    const next = new Map<string, { alarm: (typeof alarms)[number]; seenAtMs: number }>();
    for (const [id, entry] of stickyAlarmState.current) {
      if (nowMs - entry.seenAtMs <= stickyAlarmHoldMs) {
        next.set(id, entry);
      }
    }
    stickyAlarmState.current = next;
    return Array.from(next.values()).map((entry) => entry.alarm);
  }, [alarms]);

  useEffect(() => {
    if (localLayouts === null && serverLayouts.length > 0) {
      setLocalLayouts(serverLayouts);
    }
  }, [localLayouts, serverLayouts]);

  useEffect(() => {
    if (bootstrapDone || live.loading || !effectiveData) return;
    if ((localLayouts ?? serverLayouts).length > 0) {
      setBootstrapDone(true);
      return;
    }
    const bootstrap = async () => {
      try {
        const created = await api.createMultiviewLayout({
          name: "2x2",
          type: "2x2",
          is_default: true,
          tiles: buildGridTiles(2, 2),
        });
        setLocalLayouts([created]);
        setSelectedLayoutId(created.id);
      } catch {
        const refreshed = await api.getMultiviewLayouts();
        if (refreshed.layouts.length > 0) {
          setLocalLayouts(refreshed.layouts);
          const preferred =
            refreshed.layouts.find((layout) => layout.is_default) ||
            refreshed.layouts.find((layout) => layout.name === "2x2") ||
            refreshed.layouts[0];
          setSelectedLayoutId(preferred.id);
        }
      } finally {
        setBootstrapDone(true);
      }
    };
    void bootstrap();
  }, [bootstrapDone, live.loading, effectiveData, localLayouts, serverLayouts]);

  useEffect(() => {
    if (!layouts.length) {
      setSelectedLayoutId(null);
      return;
    }
    if (selectedLayoutId && layouts.some((layout) => layout.id === selectedLayoutId)) return;

    let savedId: number | null = null;
    try {
      const raw = localStorage.getItem(layoutStorageKey);
      if (raw) {
        const parsed = Number(raw);
        if (Number.isFinite(parsed)) savedId = parsed;
      }
    } catch {
      // no-op
    }
    if (savedId && layouts.some((layout) => layout.id === savedId)) {
      setSelectedLayoutId(savedId);
      return;
    }

    const preferred = layouts.find((layout) => layout.is_default) || layouts[0];
    setSelectedLayoutId(preferred.id);
  }, [layouts, selectedLayoutId]);

  useEffect(() => {
    if (selectedLayoutId == null) return;
    try {
      localStorage.setItem(layoutStorageKey, String(selectedLayoutId));
    } catch {
      // no-op
    }
  }, [selectedLayoutId]);

  const currentLayout = useMemo(
    () => layouts.find((layout) => layout.id === selectedLayoutId) ?? null,
    [layouts, selectedLayoutId]
  );
  const expectedById = useMemo(() => {
    const byId = new Map<string, ExpectedStream>();
    for (const expected of expectedItems) {
      byId.set(String(expected.stream_id || "").trim(), expected);
    }
    return byId;
  }, [expectedItems]);
  const multiviewStreams = useMemo(() => {
    const byId = new Map(streams.map((stream) => [stream.id, stream] as const));
    const liveStreamTokens = streams.map((stream) => streamMatchTokens(stream));

    for (const expected of expectedItems) {
      const streamId = String(expected.stream_id || "").trim();
      if (!streamId) continue;
      if (byId.has(streamId)) continue;
      const matchedLive = liveStreamTokens.some((tokens) => tokens.has(streamId));
      if (matchedLive) continue;
      byId.set(streamId, {
        id: streamId,
        name: expected.friendly_name || expected.umd || streamId,
        protocol: expected.expected_protocol && expected.expected_protocol !== "unknown" ? expected.expected_protocol : "unknown",
        status: "offline",
        app: streamId.includes("/") ? streamId.split("/")[0] || "unknown" : "unknown",
        stream_key: streamId.includes("/") ? streamId.split("/").slice(1).join("/") || streamId : streamId,
        source_ip: "unknown",
        uptime_seconds: 0,
        viewers_current: 0,
        outputs: {},
        metrics: {
          bitrate_kbps: 0,
          fps: expected.expected_fps ?? null,
          scan_type: "unknown",
          resolution: expected.expected_resolution || "unknown",
          video_codec: "unknown",
          audio_codec: "unknown",
        },
      });
    }

    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [streams, expectedItems]);
  const liveStreamByExpectedId = useMemo(() => {
    const match = new Map<string, Stream>();
    for (const expected of expectedItems) {
      const expectedId = String(expected.stream_id || "").trim();
      if (!expectedId) continue;
      const found = streams.find((stream) => streamMatchTokens(stream).has(expectedId));
      if (found) {
        match.set(expectedId, found);
      }
    }
    return match;
  }, [streams, expectedItems]);
  const streamById = useMemo(() => {
    const byId = new Map(multiviewStreams.map((stream) => [stream.id, stream] as const));
    const assignedStreamIds = Array.from(new Set((currentLayout?.tiles ?? []).map((tile) => tile.assigned_stream_id).filter(Boolean))) as string[];
    for (const assignedId of assignedStreamIds) {
      if (byId.has(assignedId)) continue;
      const matchedLive = liveStreamByExpectedId.get(assignedId);
      if (matchedLive) {
        byId.set(assignedId, matchedLive);
        continue;
      }
      if (/^vid-[a-z0-9]+$/i.test(assignedId) && streams.length === 1) {
        const fallbackLive = streams[0];
        byId.set(assignedId, fallbackLive);
        continue;
      }
      const expected = expectedById.get(assignedId);
      byId.set(assignedId, {
        id: assignedId,
        name: expected?.friendly_name || expected?.umd || assignedId,
        protocol: expected?.expected_protocol && expected.expected_protocol !== "unknown" ? expected.expected_protocol : "unknown",
        status: "offline",
        app: assignedId.includes("/") ? assignedId.split("/")[0] || "unknown" : "unknown",
        stream_key: assignedId.includes("/") ? assignedId.split("/").slice(1).join("/") || assignedId : assignedId,
        source_ip: "unknown",
        uptime_seconds: 0,
        viewers_current: 0,
        outputs: {},
        metrics: {
          bitrate_kbps: 0,
          fps: expected?.expected_fps ?? null,
          scan_type: "unknown",
          resolution: expected?.expected_resolution || "unknown",
          video_codec: "unknown",
          audio_codec: "unknown",
        },
      });
    }
    return byId;
  }, [multiviewStreams, currentLayout, expectedById, liveStreamByExpectedId, streams]);

  useEffect(() => {
    if (!currentLayout) return;
    const nowMs = Date.now();
    const retryUnavailableMs = 5000;
    const assigned = Array.from(new Set(currentLayout.tiles.map((tile) => tile.assigned_stream_id).filter(Boolean))) as string[];
    for (const assignedId of assigned) {
      const resolved = streamById.get(assignedId);
      const previewStreamId = resolved?.id ?? assignedId;
      const existingPreview = previewByStream[previewStreamId];
      const isOffline = resolved?.status === "offline";
      if (existingPreview !== undefined) {
        if (isOffline || existingPreview === null || existingPreview.state !== "preview_unavailable") {
          continue;
        }
        const lastRetry = previewRetryAtRef.current[previewStreamId] ?? 0;
        if (nowMs - lastRetry < retryUnavailableMs) {
          continue;
        }
      } else {
        setPreviewByStream((prev) => ({ ...prev, [previewStreamId]: null }));
      }
      previewRetryAtRef.current[previewStreamId] = nowMs;
      void api.getPreviewUrl(previewStreamId).then((result) => {
        setPreviewByStream((prev) => ({
          ...prev,
          [previewStreamId]: {
            ...result,
            playback_url: normalizePlaybackUrl(result.playback_url),
          }
        }));
      }).catch(() => {
        setPreviewByStream((prev) => ({
          ...prev,
          [previewStreamId]: {
            stream_id: previewStreamId,
            state: "preview_unavailable",
            source: "none",
            playback_url: null,
            reason: "preview_request_failed"
          }
        }));
      });
    }
  }, [currentLayout, previewByStream, streamById]);

  useEffect(() => {
    const previews = live.liveBundle?.preview?.previews;
    if (!Array.isArray(previews)) return;
    const updates: Record<string, PreviewResolveResponse> = {};
    for (const item of previews) {
      const streamId = typeof item.stream_id === "string" ? item.stream_id : null;
      if (!streamId) continue;
      const state = item.state === "running" ? "preview_started" : item.state === "preview_unavailable" ? "preview_unavailable" : "preview_started";
      updates[streamId] = {
        stream_id: streamId,
        state,
        source: "preview_hls",
        playback_url: normalizePlaybackUrl(typeof item.preview_url === "string" ? item.preview_url : null),
        reason: typeof item.reason === "string" ? item.reason : null
      };
    }
    if (!Object.keys(updates).length) return;
    setPreviewByStream((prev) => ({ ...prev, ...updates }));
  }, [live.liveBundle]);

  const saveLayout = useCallback(async (layout: MultiviewLayout, nextTiles: MultiviewTile[], nextName?: string, nextType?: MultiviewLayoutType) => {
    setLocalLayouts((prev) =>
      (prev ?? layouts).map((item) =>
        item.id === layout.id
          ? {
              ...item,
              name: nextName ?? item.name,
              type: nextType ?? item.type,
              tiles: nextTiles
            }
          : item
      )
    );
    await api.updateMultiviewLayout(layout.id, {
      name: nextName ?? layout.name,
      type: nextType ?? layout.type,
      is_default: layout.is_default,
      tiles: nextTiles
    });
  }, [layouts]);

  const assignStream = useCallback(async (tileId: string, streamId: string | null) => {
    if (!currentLayout) return;
    const selected = streamId ? streamById.get(streamId) : undefined;
    const expected = selected ? resolveExpectedForStream(selected, expectedItems) : undefined;
    const stableAssignedId = streamId && expected ? expected.stream_id : streamId;
    const nextTiles = currentLayout.tiles.map((tile) =>
      tile.id === tileId
        ? {
            ...tile,
            assigned_stream_id: stableAssignedId,
            muted: stableAssignedId ? true : tile.muted
          }
        : tile
    );
    await saveLayout(currentLayout, nextTiles);
  }, [currentLayout, saveLayout, streamById, expectedItems]);

  const toggleTileMute = useCallback(async (tileId: string) => {
    if (!currentLayout) return;
    const nextTiles = currentLayout.tiles.map((tile) => (tile.id === tileId ? { ...tile, muted: !tile.muted } : tile));
    await saveLayout(currentLayout, nextTiles);
  }, [currentLayout, saveLayout]);
  const toggleTileOverlay = useCallback(async (tileId: string) => {
    if (!currentLayout) return;
    const nextTiles = currentLayout.tiles.map((tile) =>
      tile.id === tileId ? { ...tile, show_overlay: tile.show_overlay === false ? true : false } : tile
    );
    await saveLayout(currentLayout, nextTiles);
  }, [currentLayout, saveLayout]);

  const detectPresetKey = useCallback((layout: MultiviewLayout | null): string => {
    if (!layout) return "2x2";
    const rows = Math.max(...layout.tiles.map((tile) => tile.row + tile.row_span), 0);
    const cols = Math.max(...layout.tiles.map((tile) => tile.column + tile.column_span), 0);
    if (rows === 1 && cols === 2) return "1x2";
    if (rows === 2 && cols === 2) return "2x2";
    if (rows === 2 && cols === 3) return "2x3";
    if (rows === 3 && cols === 3) return "3x3";
    if (rows === 4 && cols === 4) return "4x4";
    return "2x2";
  }, []);

  const applyPreset = useCallback(async (presetKey: string) => {
    const preset = presetOptions.find((item) => item.key === presetKey);
    if (!preset) return;

    const baseLayouts = localLayouts ?? layouts;
    const existing = baseLayouts.find((layout) => layout.name === preset.label);
    if (existing) {
      setSelectedLayoutId(existing.id);
      return;
    }

    const created = await api.createMultiviewLayout({
      name: preset.label,
      type: preset.layoutType,
      is_default: false,
      tiles: buildGridTiles(preset.rows, preset.cols),
    });
    setLocalLayouts((prev) => [created, ...(prev ?? layouts)]);
    setSelectedLayoutId(created.id);
  }, [layouts, localLayouts, presetOptions]);

  const setDefault = async () => {
    if (!currentLayout) return;
    await api.setDefaultMultiviewLayout(currentLayout.id);
    setLocalLayouts((prev) =>
      (prev ?? layouts).map((item) => ({ ...item, is_default: item.id === currentLayout.id }))
    );
  };

  const onMuteAll = async () => {
    if (!currentLayout) return;
    const next = !currentLayout.tiles.every((tile) => tile.muted);
    const nextTiles = currentLayout.tiles.map((tile) => ({ ...tile, muted: next }));
    await saveLayout(currentLayout, nextTiles);
  };

  const onFullscreen = async () => {
    const el = hostRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      await el.requestFullscreen();
      setFullscreen(true);
    } else {
      await document.exitFullscreen();
      setFullscreen(false);
    }
  };

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const runFlipAnimation = useCallback((tileId: string, from: DOMRect) => {
    const tileEl = tileRefs.current[tileId];
    if (!tileEl) return;
    const to = tileEl.getBoundingClientRect();
    const dx = from.left - to.left;
    const dy = from.top - to.top;
    const sx = from.width / Math.max(to.width, 1);
    const sy = from.height / Math.max(to.height, 1);
    tileEl.style.transformOrigin = "top left";
    tileEl.style.transition = "none";
    tileEl.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
    tileEl.getBoundingClientRect();
    tileEl.style.transition = "transform 260ms cubic-bezier(0.22, 0.61, 0.36, 1)";
    tileEl.style.transform = "translate(0px, 0px) scale(1, 1)";
    const onDone = () => {
      tileEl.style.transition = "";
      tileEl.style.transform = "";
      tileEl.style.transformOrigin = "";
      tileEl.removeEventListener("transitionend", onDone);
      setSoloAnimating(false);
    };
    tileEl.addEventListener("transitionend", onDone);
    window.setTimeout(onDone, 350);
  }, []);

  const expandToSolo = useCallback((tileId: string) => {
    if (soloAnimating || soloTileId === tileId) return;
    const tileEl = tileRefs.current[tileId];
    if (!tileEl) {
      setSoloTileId(tileId);
      return;
    }
    const from = tileEl.getBoundingClientRect();
    setSoloAnimating(true);
    setSoloTileId(tileId);
    window.requestAnimationFrame(() => runFlipAnimation(tileId, from));
  }, [runFlipAnimation, soloAnimating, soloTileId]);

  const collapseSolo = useCallback(() => {
    if (soloAnimating || !soloTileId) return;
    const tileEl = tileRefs.current[soloTileId];
    if (!tileEl) {
      setSoloTileId(null);
      return;
    }
    const from = tileEl.getBoundingClientRect();
    const tileId = soloTileId;
    setSoloAnimating(true);
    setSoloTileId(null);
    window.requestAnimationFrame(() => runFlipAnimation(tileId, from));
  }, [runFlipAnimation, soloAnimating, soloTileId]);

  if (live.loading) return <LoadingState />;
  if (live.error || !effectiveData) return <ErrorState error={live.error || "Failed loading multiviewer data"} />;
  if (layouts.length === 0) return <LoadingState />;

  return (
    <section className={`panel multiview-root ${fullscreen ? "noc-fullscreen" : ""}`} ref={hostRef}>
      <div className="mv-toolbar">
        <h2>Multiviewer</h2>
        <div className="mv-toolbar-actions">
          <select value={detectPresetKey(currentLayout)} onChange={(e) => void applyPreset(e.target.value)} disabled={!currentLayout}>
            {presetOptions.map((preset) => (
              <option key={preset.key} value={preset.key}>{preset.label}</option>
            ))}
          </select>
          <button onClick={() => void setDefault()} disabled={!currentLayout}>Set Default</button>
          <button onClick={() => void onMuteAll()}>{currentLayout?.tiles.every((tile) => tile.muted) ? "Unmute All" : "Mute All"}</button>
          {soloTileId ? <button onClick={() => collapseSolo()}>Back to layout</button> : null}
          <button onClick={() => void onFullscreen()}>{fullscreen ? "Exit Fullscreen" : "Fullscreen NOC"}</button>
        </div>
      </div>

      <div className={`mv-layout ${alertsDrawerOpen ? "drawer-open" : "drawer-collapsed"}`}>
        <aside className="mv-stream-list">
          <h3>Streams</h3>
          {multiviewStreams.map((stream) => (
            <button
              key={stream.id}
              className={`mv-stream-chip status-${stream.status}`}
              draggable
              onDragStart={(e) => e.dataTransfer.setData("text/plain", stream.id)}
            >
              <strong>{stream.name}</strong>
              <span>{stream.id}</span>
            </button>
          ))}
        </aside>

        <div ref={gridRef} className={`mv-grid type-${detectPresetKey(currentLayout)} ${soloTileId ? "solo-mode" : ""}`}>
          {(currentLayout?.tiles ?? []).map((tile) => {
            const stream = tile.assigned_stream_id ? streamById.get(tile.assigned_stream_id) : undefined;
            const preview = stream ? previewByStream[stream.id] : null;
            const expected = stream ? resolveExpectedForStream(stream, expectedItems) : undefined;
            const activeStreamAlarms = stream
              ? activeAlarms.filter((a) => {
                  if (!a.stream_id) return false;
                  return alarmMatchesStream(a.stream_id, stream);
                })
              : [];
            const alarm = activeStreamAlarms[0];
            const isOffline = Boolean(stream && stream.status === "offline");
            const hasCriticalAlarm = isOffline || activeStreamAlarms.some((a) => a.severity === "critical");
            const hasWarningAlarm = !hasCriticalAlarm && activeStreamAlarms.some((a) => a.severity === "warning");
            const showUmd = tile.show_overlay !== false;
            const isSolo = !soloTileId || soloTileId === tile.id;
            const isSoloActive = soloTileId === tile.id;
            const state =
              !stream ? "No stream assigned" :
              isOffline ? "Offline" :
              preview === undefined || preview === null ? "Loading" :
              preview.state === "preview_unavailable" ? "Preview unavailable" : "Live";
            const playbackUrl = preview?.playback_url ?? null;

            return (
              <article
                key={tile.id}
                ref={(el) => {
                  tileRefs.current[tile.id] = el;
                }}
                className={`mv-tile ${isSolo ? "" : "hidden"} ${isSoloActive ? "solo-active" : ""} ${state.toLowerCase().replace(/\s+/g, "-")} ${hasCriticalAlarm ? "alarm-critical" : hasWarningAlarm ? "alarm-warning" : ""}`}
                style={
                  isSoloActive
                    ? {
                        position: "absolute",
                        inset: "8px",
                        zIndex: 20,
                        gridColumn: "auto",
                        gridRow: "auto",
                      }
                    : {
                        gridColumn: `${tile.column + 1} / span ${tile.column_span}`,
                        gridRow: `${tile.row + 1} / span ${tile.row_span}`,
                      }
                }
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const streamId = e.dataTransfer.getData("text/plain");
                  if (streamId) void assignStream(tile.id, streamId);
                }}
                onClick={() => {
                  if (soloTileId === tile.id) {
                    void collapseSolo();
                    return;
                  }
                  void expandToSolo(tile.id);
                }}
              >
                {isOffline ? <div className="mv-offline-banner">Stream Offline</div> : null}
                {playbackUrl && state === "Live" ? (
                  <TilePlayer
                    playbackUrl={playbackUrl}
                    muted={tile.muted}
                    scanType={stream?.metrics.scan_type ?? "unknown"}
                    protocol={stream?.protocol}
                  >
                    <div className="mv-state">{state}{preview?.reason ? `: ${preview.reason}` : ""}</div>
	                    <div className="mv-overlay">
	                      <div className="mv-ov-head">
	                        <span>{expected?.umd || expected?.friendly_name || stream?.name || "Unassigned"}</span>
	                        <span className="mv-ov-head-right">
	                          {stream ? <span className="mv-playback-badge">{playbackSourceLabel(preview?.source)}</span> : null}
	                          {alarm ? <span className="mv-alarm">ALARM</span> : null}
	                        </span>
	                      </div>
                      {showUmd ? (
                        <div className="mv-meta">
                          <span>ID: {stream?.id ?? "-"}</span>
                          <span>Protocol: {stream?.protocol ?? "-"}</span>
                          <span>In: {stream?.metrics.bitrate_kbps ?? 0} kbps</span>
                          <span>Out: {stream ? stream.viewers_current * Math.max(Math.floor((stream.metrics.bitrate_kbps ?? 0) * 0.35), 200) : 0} kbps</span>
                          <span>Res: {stream?.metrics.resolution ?? "-"}</span>
                          <span>FPS: {formatFps(stream?.metrics.fps)}</span>
                          <span>Scan: {stream?.metrics.scan_type ?? "-"}</span>
                          <span>Codec: {stream?.metrics.video_codec ?? "-"}</span>
                          <span>Source: {stream?.source_ip ?? "-"}</span>
                          <span>Viewers: {stream?.viewers_current ?? 0}</span>
                          <span>Health: {stream?.status ?? "-"}</span>
                          <span>Last Error: {alarm?.title ?? "-"}</span>
                        </div>
                      ) : null}
                    </div>
                    <div className="mv-controls">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void toggleTileOverlay(tile.id);
                        }}
                      >
                        {showUmd ? "UMD Off" : "UMD On"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void toggleTileMute(tile.id);
                        }}
                      >
                        {tile.muted ? "Unmute" : "Mute"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void assignStream(tile.id, null);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  </TilePlayer>
                ) : (
                  <>
                    <div className="mv-state">{state}{preview?.reason ? `: ${preview.reason}` : ""}</div>
	                    <div className="mv-overlay">
	                      <div className="mv-ov-head">
	                        <span>{expected?.umd || expected?.friendly_name || stream?.name || "Unassigned"}</span>
	                        <span className="mv-ov-head-right">
	                          {stream ? <span className="mv-playback-badge">{playbackSourceLabel(preview?.source)}</span> : null}
	                          {alarm ? <span className="mv-alarm">ALARM</span> : null}
	                        </span>
	                      </div>
                      {showUmd ? (
                        <div className="mv-meta">
                          <span>ID: {stream?.id ?? "-"}</span>
                          <span>Protocol: {stream?.protocol ?? "-"}</span>
                          <span>In: {stream?.metrics.bitrate_kbps ?? 0} kbps</span>
                          <span>Out: {stream ? stream.viewers_current * Math.max(Math.floor((stream.metrics.bitrate_kbps ?? 0) * 0.35), 200) : 0} kbps</span>
                          <span>Res: {stream?.metrics.resolution ?? "-"}</span>
                          <span>FPS: {formatFps(stream?.metrics.fps)}</span>
                          <span>Scan: {stream?.metrics.scan_type ?? "-"}</span>
                          <span>Codec: {stream?.metrics.video_codec ?? "-"}</span>
                          <span>Source: {stream?.source_ip ?? "-"}</span>
                          <span>Viewers: {stream?.viewers_current ?? 0}</span>
                          <span>Health: {stream?.status ?? "-"}</span>
                          <span>Last Error: {alarm?.title ?? "-"}</span>
                        </div>
                      ) : null}
                    </div>
                    <div className="mv-controls">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void toggleTileOverlay(tile.id);
                        }}
                      >
                        {showUmd ? "UMD Off" : "UMD On"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void toggleTileMute(tile.id);
                        }}
                      >
                        {tile.muted ? "Unmute" : "Mute"}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void assignStream(tile.id, null);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  </>
                )}
              </article>
            );
          })}
        </div>
        <aside className={`mv-alerts-drawer ${alertsDrawerOpen ? "open" : "collapsed"}`}>
          <button className="mv-alerts-toggle" onClick={() => setAlertsDrawerOpen((v) => !v)}>
            {alertsDrawerOpen ? "Alerts ▸" : "◂ Alerts"}
          </button>
          {alertsDrawerOpen ? (
            <div className="mv-alerts-body">
              <h3>Active Alerts</h3>
              <ul className="events-list">
                {activeAlarms.slice(0, 50).map((alarm) => (
                  <li key={`${alarm.id}-${alarm.last_seen}`} className="event-row">
                    <span className={`health health-${alarm.severity === "critical" ? "red" : alarm.severity === "warning" ? "yellow" : "green"}`}>{alarm.severity}</span>
                    <span className="event-title">{alarm.title}</span>
                    <span className="event-time">{alarm.stream_id || "-"}</span>
                  </li>
                ))}
                {activeAlarms.length === 0 ? (
                  <li className="event-row"><span className="event-title">No active alerts</span></li>
                ) : null}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

export function SettingsPage() {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const host = publicHost();
  const appName = "live";
  const streamKey = "<stream-key>";
  const appStream = `${appName}/${streamKey}`;
  const backendUrl = resolveBackendUrlForDisplay(host);
  const rtmpPort = frontendEnv("VITE_SRS_RTMP_PORT", "1935");
  const srtPort = frontendEnv("VITE_SRS_SRT_PORT", "10080");
  const httpBase = resolveSrsHttpBaseUrl(host);
  const webrtcBase = frontendEnv("VITE_SRS_PUBLIC_WEBRTC_BASE_URL", `webrtc://${host}`).replace(/\/$/, "");
  const ingestFormats = [
    {
      key: "rtmp",
      format: "RTMP",
      primaryLabel: "Full publish URL",
      primaryUrl: `rtmp://${host}:${rtmpPort}/${appStream}`,
      details: [
        { label: "Server", value: `rtmp://${host}:${rtmpPort}/${appName}` },
        { label: "Stream key", value: streamKey }
      ]
    },
    {
      key: "srt",
      format: "SRT",
      primaryLabel: "Full publish URL",
      primaryUrl: `srt://${host}:${srtPort}?streamid=#!::r=${appStream},m=publish`,
      details: [
        { label: "Listener", value: `srt://${host}:${srtPort}` },
        { label: "Stream ID", value: `#!::r=${appStream},m=publish` }
      ]
    }
  ];

  async function copyValue(key: string, value: string) {
    const copied = await copyText(value);
    if (copied) {
      setCopiedKey(key);
      window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current));
      }, 1400);
    }
  }

  return (
    <section className="panel settings-panel">
      <h2>Settings</h2>
      <div className="settings-meta-grid">
        <div className="settings-item">
          <div className="settings-item-label">Backend API URL</div>
          <code>{backendUrl}</code>
        </div>
        <div className="settings-item">
          <div className="settings-item-label">SRS HTTP Base</div>
          <code>{httpBase}</code>
        </div>
        <div className="settings-item">
          <div className="settings-item-label">SRS WebRTC Base</div>
          <code>{webrtcBase}</code>
        </div>
      </div>

      <h3 className="subhead">Ingest URLs</h3>
      <div className="settings-table-wrap">
        <table className="table settings-url-table">
          <thead>
            <tr>
              <th>Format</th>
              <th>URL</th>
              <th>Publisher Fields</th>
            </tr>
          </thead>
          <tbody>
            {ingestFormats.map((item) => (
              <tr key={item.key}>
                <td>
                  <span className="health health-green">{item.format}</span>
                </td>
                <td>
                  <div className="settings-url-stack">
                    <span className="settings-item-label">{item.primaryLabel}</span>
                    <div className="settings-copy-row">
                      <code>{item.primaryUrl}</code>
                      <button className="btn-xs" onClick={() => void copyValue(item.key, item.primaryUrl)}>
                        {copiedKey === item.key ? "Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                </td>
                <td>
                  <div className="settings-url-stack">
                    {item.details.map((detail) => (
                      <div className="settings-detail-row" key={detail.label}>
                        <span>{detail.label}</span>
                        <code>{detail.value}</code>
                      </div>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
