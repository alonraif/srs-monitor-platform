import { useEffect, useRef, useState } from "react";
import type { Alarm, AlarmsResponse } from "./types";
import type { LiveBundle } from "./types";
import { LIVE_URL } from "./api";

export function useAutoRefresh<T>(loader: () => Promise<T>, intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    async function refresh(initial = false) {
      if (initial) {
        setLoading(true);
      }
      try {
        const next = await loader();
        if (!mounted.current) {
          return;
        }
        setData(next);
        setError(null);
      } catch (err) {
        if (!mounted.current) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (mounted.current) {
          setLoading(false);
        }
      }
    }

    refresh(true);
    const timer = window.setInterval(() => refresh(false), intervalMs);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
    };
  }, [loader, intervalMs]);

  return { data, error, loading };
}

export interface AlarmHistoryEvent {
  id: string;
  alarm_id: string;
  action: "activated" | "acknowledged" | "unacknowledged" | "resolved";
  severity: Alarm["severity"];
  title: string;
  stream_id: string | null;
  timestamp: string;
}

export interface AlarmFeed {
  generated_at: string;
  active: Alarm[];
  resolved: Alarm[];
  history: AlarmHistoryEvent[];
}

const RESOLVED_KEY = "srs_monitor_resolved_alarms";
const HISTORY_KEY = "srs_monitor_alarm_history";

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveJson<T>(key: string, value: T) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // best-effort persistence
  }
}

export function useAlarmFeed(loader: () => Promise<AlarmsResponse>, intervalMs = 5000) {
  const [data, setData] = useState<AlarmFeed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);
  const previousActive = useRef<Map<string, Alarm>>(new Map());
  const resolvedStore = useRef<Alarm[]>([]);
  const historyStore = useRef<AlarmHistoryEvent[]>([]);
  const seeded = useRef(false);

  useEffect(() => {
    mounted.current = true;
    if (!seeded.current) {
      resolvedStore.current = loadJson<Alarm[]>(RESOLVED_KEY, []);
      historyStore.current = loadJson<AlarmHistoryEvent[]>(HISTORY_KEY, []);
      seeded.current = true;
    }

    function pushHistory(event: AlarmHistoryEvent) {
      historyStore.current = [event, ...historyStore.current].slice(0, 300);
      saveJson(HISTORY_KEY, historyStore.current);
    }

    async function refresh(initial = false) {
      if (initial) setLoading(true);
      try {
        const next = await loader();
        if (!mounted.current) return;

        const nowIso = new Date().toISOString();
        const currentMap = new Map(next.alarms.map((alarm) => [alarm.id, alarm] as const));

        for (const [id, prev] of previousActive.current) {
          if (!currentMap.has(id)) {
            const resolvedAlarm: Alarm = {
              ...prev,
              status: "resolved",
              resolved_at: nowIso,
              last_seen: nowIso
            };
            resolvedStore.current = [resolvedAlarm, ...resolvedStore.current.filter((item) => item.id !== id)].slice(0, 200);
            saveJson(RESOLVED_KEY, resolvedStore.current);
            pushHistory({
              id: `${id}-resolved-${nowIso}`,
              alarm_id: id,
              action: "resolved",
              severity: prev.severity,
              title: prev.title,
              stream_id: prev.stream_id,
              timestamp: nowIso
            });
          }
        }

        for (const alarm of next.alarms) {
          const prev = previousActive.current.get(alarm.id);
          if (!prev) {
            pushHistory({
              id: `${alarm.id}-activated-${nowIso}`,
              alarm_id: alarm.id,
              action: "activated",
              severity: alarm.severity,
              title: alarm.title,
              stream_id: alarm.stream_id,
              timestamp: nowIso
            });
          } else if (prev.status !== alarm.status) {
            pushHistory({
              id: `${alarm.id}-${alarm.status}-${nowIso}`,
              alarm_id: alarm.id,
              action: alarm.status === "acknowledged" ? "acknowledged" : "unacknowledged",
              severity: alarm.severity,
              title: alarm.title,
              stream_id: alarm.stream_id,
              timestamp: nowIso
            });
          }
        }

        previousActive.current = currentMap;
        setData({
          generated_at: next.generated_at,
          active: next.alarms,
          resolved: resolvedStore.current,
          history: historyStore.current
        });
        setError(null);
      } catch (err) {
        if (!mounted.current) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (mounted.current) setLoading(false);
      }
    }

    refresh(true);
    const timer = window.setInterval(() => refresh(false), intervalMs);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
    };
  }, [loader, intervalMs]);

  return { data, error, loading };
}

export function useLiveBundle<T>(
  pollLoader: () => Promise<T>,
  merge: (current: T | null, live: LiveBundle) => T,
  pollIntervalMs = 5000
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [liveConnected, setLiveConnected] = useState(false);
  const [liveBundle, setLiveBundle] = useState<LiveBundle | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    let source: EventSource | null = null;
    let fallbackTimer: number | null = null;

    const runPoll = async (initial = false) => {
      if (initial) setLoading(true);
      try {
        const next = await pollLoader();
        if (!mounted.current) return;
        setData(next);
        setError(null);
      } catch (err) {
        if (!mounted.current) return;
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (mounted.current) setLoading(false);
      }
    };

    const startPollingFallback = () => {
      if (fallbackTimer !== null) return;
      fallbackTimer = window.setInterval(() => {
        void runPoll(false);
      }, pollIntervalMs);
    };

    const stopPollingFallback = () => {
      if (fallbackTimer === null) return;
      window.clearInterval(fallbackTimer);
      fallbackTimer = null;
    };

    void runPoll(true);
    try {
      source = new EventSource(LIVE_URL);
      source.addEventListener("live", (event) => {
        if (!mounted.current) return;
        try {
          const payload = JSON.parse((event as MessageEvent).data) as LiveBundle;
          setLiveBundle(payload);
          setData((prev) => merge(prev, payload));
          setError(null);
          setLiveConnected(true);
          setLoading(false);
          stopPollingFallback();
        } catch {
          setLiveConnected(false);
          startPollingFallback();
        }
      });
      source.onerror = () => {
        if (!mounted.current) return;
        setLiveConnected(false);
        startPollingFallback();
      };
    } catch {
      setLiveConnected(false);
      startPollingFallback();
    }

    return () => {
      mounted.current = false;
      if (source) source.close();
      stopPollingFallback();
    };
  }, [merge, pollIntervalMs, pollLoader]);

  return { data, error, loading, liveConnected, liveBundle };
}
