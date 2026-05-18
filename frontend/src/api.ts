import type {
  Alarm,
  AlarmsResponse,
  ClientsResponse,
  DashboardResponse,
  ExpectedStream,
  ExpectedStreamsResponse,
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
  const inferredBackendUrl = window.location.origin;
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
const BACKEND_API_KEY = (import.meta.env.VITE_BACKEND_API_KEY as string | undefined)?.trim() || "";

function authHeaders(): Record<string, string> {
  if (!BACKEND_API_KEY) return {};
  return { Authorization: `Bearer ${BACKEND_API_KEY}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
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
        headers: { "Content-Type": "application/json", ...authHeaders() }
      });
      if (primary.ok) {
        previewUrlRouteSupported = true;
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
      headers: { "Content-Type": "application/json", ...authHeaders() },
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
