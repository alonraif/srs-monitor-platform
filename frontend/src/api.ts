import type {
  Alarm,
  AlarmsResponse,
  ClientsResponse,
  DashboardResponse,
  ExpectedStream,
  ExpectedStreamsResponse,
  GlobalSrtSecurityConfig,
  MultiviewLayout,
  MultiviewLayoutsResponse,
  MultiviewTile,
  PreviewResolveResponse,
  Stream,
  StreamNotesResponse,
  StreamsResponse,
  SystemResponse
} from "./types";

function resolveBackendUrl(): string {
  const current = new URL(window.location.origin);
  const inferredBackendUrl =
    import.meta.env.DEV && current.port === "3000"
      ? `${current.protocol}//${current.hostname}:8000`
      : current.origin;
  const configured = (import.meta.env.VITE_BACKEND_API_URL as string | undefined)?.trim();
  if (!configured) return inferredBackendUrl;
  try {
    const parsed = new URL(configured, inferredBackendUrl);
    if (!parsed.hostname) {
      return inferredBackendUrl;
    }
    const isLocalhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    const isRemoteBrowser = !["localhost", "127.0.0.1"].includes(window.location.hostname);
    if (isLocalhost && isRemoteBrowser) {
      parsed.hostname = window.location.hostname;
      return parsed.toString().replace(/\/$/, "");
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return inferredBackendUrl;
  }
}

const BASE_URL = resolveBackendUrl();
export const LIVE_URL = `${BASE_URL}/api/live`;
let previewUrlRouteSupported: boolean | null = null;
const SESSION_STORAGE_KEY = "srs_monitor_session_token";
const BACKEND_READ_API_KEY = (import.meta.env.VITE_BACKEND_API_KEY as string | undefined)?.trim() || "";
const BACKEND_WRITE_API_KEY =
  (import.meta.env.VITE_BACKEND_WRITE_API_KEY as string | undefined)?.trim() || BACKEND_READ_API_KEY;

export function getSessionToken(): string {
  return window.localStorage.getItem(SESSION_STORAGE_KEY) || "";
}

export function setSessionToken(token: string | null): void {
  if (!token) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, token);
}

function authHeaders(method = "GET"): Record<string, string> {
  const upper = method.toUpperCase();
  const isSafe = upper === "GET" || upper === "HEAD" || upper === "OPTIONS";
  const token = isSafe ? BACKEND_READ_API_KEY : BACKEND_WRITE_API_KEY;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const mergedHeaders = {
    "Content-Type": "application/json",
    "x-session-token": getSessionToken(),
    ...authHeaders(method),
    ...((init?.headers as Record<string, string> | undefined) || {}),
  };
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: mergedHeaders,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  const text = await response.text();
  const snippet = text.slice(0, 140).trim();
  throw new Error(
    `Expected JSON from ${path}, got ${contentType || "unknown content-type"}.` +
      (snippet ? ` Response starts with: ${snippet}` : "")
  );
}

export const api = {
  login: (password: string) =>
    request<{ token: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  getSession: () => request<{ authenticated: boolean }>("/api/auth/session"),
  getDashboard: () => request<DashboardResponse>("/api/dashboard"),
  getSystem: () => request<SystemResponse>("/api/system"),
  getStreams: () => request<StreamsResponse>("/api/streams"),
  getStream: (id: string) => request<Stream>(`/api/streams/${id}`),
  getStreamNotes: (id: string) => request<StreamNotesResponse>(`/api/streams/${id}/notes`),
  updateStreamNotes: (id: string, note: string, author = "ui-operator") =>
    request<StreamNotesResponse>(`/api/streams/${id}/notes`, {
      method: "PUT",
      body: JSON.stringify({ note, author })
    }),
  getClients: () => request<ClientsResponse>("/api/clients"),
  getAlarms: () => request<AlarmsResponse>("/api/alarms"),
  ackAlarm: (id: string) =>
    request<Alarm>(`/api/alarms/${id}/ack`, { method: "POST", headers: { "x-operator": "ui-operator" } }),
  unackAlarm: (id: string) =>
    request<Alarm>(`/api/alarms/${id}/unack`, { method: "POST", headers: { "x-operator": "ui-operator" } }),
  getExpectedStreams: () => request<ExpectedStreamsResponse>("/api/config/streams"),
  createExpectedStream: (payload: Omit<ExpectedStream, "id" | "created_at" | "updated_at">) =>
    request<ExpectedStream>("/api/config/streams", { method: "POST", body: JSON.stringify(payload) }),
  updateExpectedStream: (streamId: string, payload: Omit<ExpectedStream, "id" | "stream_id" | "created_at" | "updated_at">) =>
    request<ExpectedStream>(`/api/config/streams/${streamId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteExpectedStream: (streamId: string) => request<void>(`/api/config/streams/${streamId}`, { method: "DELETE" }),
  getGlobalSrtSecurity: () => request<GlobalSrtSecurityConfig>("/api/config/srt-security"),
  updateGlobalSrtSecurity: (payload: { srt_encryption_required: boolean; srt_pbkeylen: number; srt_passphrase?: string | null }) =>
    request<GlobalSrtSecurityConfig>("/api/config/srt-security", { method: "PUT", body: JSON.stringify(payload) }),
  getMultiviewLayouts: () => request<MultiviewLayoutsResponse>("/api/multiview/layouts"),
  createMultiviewLayout: (payload: { name: string; type: MultiviewLayout["type"]; is_default: boolean; tiles: MultiviewTile[] }) =>
    request<MultiviewLayout>("/api/multiview/layouts", { method: "POST", body: JSON.stringify(payload) }),
  getMultiviewLayout: (id: number) => request<MultiviewLayout>(`/api/multiview/layouts/${id}`),
  updateMultiviewLayout: (id: number, payload: { name: string; type: MultiviewLayout["type"]; is_default: boolean; tiles: MultiviewTile[] }) =>
    request<MultiviewLayout>(`/api/multiview/layouts/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteMultiviewLayout: (id: number) => request<{ deleted: boolean }>(`/api/multiview/layouts/${id}`, { method: "DELETE" }),
  setDefaultMultiviewLayout: (id: number) => request<MultiviewLayout>(`/api/multiview/layouts/${id}/set-default`, { method: "POST" }),
  getPreviewUrl: async (streamId: string) => {
    if (previewUrlRouteSupported !== false) {
      const primary = await fetch(`${BASE_URL}/api/preview/url/${streamId}`, {
        headers: { "Content-Type": "application/json", ...authHeaders("GET") }
      });
      if (primary.ok) {
        previewUrlRouteSupported = true;
        const contentType = (primary.headers.get("content-type") || "").toLowerCase();
        if (!contentType.includes("application/json")) {
          const text = await primary.text();
          const snippet = text.slice(0, 140).trim();
          throw new Error(
            `Expected JSON from /api/preview/url/${streamId}, got ${contentType || "unknown content-type"}.` +
              (snippet ? ` Response starts with: ${snippet}` : "")
          );
        }
        return (await primary.json()) as PreviewResolveResponse;
      }
      if (primary.status !== 404) {
        const text = await primary.text();
        throw new Error(text || `Request failed with ${primary.status}`);
      }
      previewUrlRouteSupported = false;
    }
    // Compatibility fallback for older backends that don't expose /preview/url.
    const fallback = await fetch(`${BASE_URL}/api/preview/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders("POST") },
      body: JSON.stringify({ stream_id: streamId, inactivity_timeout_seconds: 60 })
    });
    if (fallback.status === 404) {
      return {
        stream_id: streamId,
        state: "preview_unavailable",
        source: "none",
        playback_url: null,
        reason: "stream_not_found"
      };
    }
    if (!fallback.ok) {
      const text = await fallback.text();
      throw new Error(text || `Request failed with ${fallback.status}`);
    }
    const contentType = (fallback.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("application/json")) {
      const text = await fallback.text();
      const snippet = text.slice(0, 140).trim();
      throw new Error(
        `Expected JSON from /api/preview/start, got ${contentType || "unknown content-type"}.` +
          (snippet ? ` Response starts with: ${snippet}` : "")
      );
    }
    return (await fallback.json()) as PreviewResolveResponse;
  },
  startPreview: (streamId: string, inactivity_timeout_seconds = 60) =>
    request<PreviewResolveResponse>("/api/preview/start", {
      method: "POST",
      body: JSON.stringify({ stream_id: streamId, inactivity_timeout_seconds })
    }),
  stopPreview: (streamId: string) =>
    request<{ stream_id: string; state: string }>("/api/preview/stop", {
      method: "POST",
      body: JSON.stringify({ stream_id: streamId })
    })
};
