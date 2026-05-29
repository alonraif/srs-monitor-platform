import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, getSessionToken, setSessionToken } from "./api";

const IDLE_MINUTES_KEY = "srs_monitor_idle_logout_minutes";

interface AuthContextValue {
  isAuthenticated: boolean;
  logoutReason: "idle" | null;
  idleLogoutMinutes: number;
  setIdleLogoutMinutes: (minutes: number) => void;
  login: (password: string) => Promise<boolean>;
  logout: (reason?: "idle" | "manual") => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function parseIdleMinutes(value: string | null): number {
  if (!value) return 0;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return n;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string>(() => getSessionToken());
  const [logoutReason, setLogoutReason] = useState<"idle" | null>(null);
  const [idleLogoutMinutes, setIdleLogoutMinutesState] = useState<number>(() => parseIdleMinutes(window.localStorage.getItem(IDLE_MINUTES_KEY)));
  const timeoutRef = useRef<number | null>(null);

  const isAuthenticated = Boolean(token);

  useEffect(() => {
    setSessionToken(token || null);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let mounted = true;
    void api
      .getSession()
      .then((response) => {
        if (mounted && !response.authenticated) {
          setToken("");
        }
      })
      .catch(() => {
        if (mounted) setToken("");
      });
    return () => {
      mounted = false;
    };
  }, [token]);

  const logout = async (reason: "idle" | "manual" = "manual") => {
    try {
      await api.logout();
    } catch {
      // Ignore network/logout errors and clear local session anyway.
    }
    setToken("");
    setLogoutReason(reason === "idle" ? "idle" : null);
  };

  const login = async (password: string) => {
    try {
      const response = await api.login(password);
      setToken(response.token || "");
      setLogoutReason(null);
      return Boolean(response.token);
    } catch {
      return false;
    }
  };

  const setIdleLogoutMinutes = (minutes: number) => {
    const safe = Number.isFinite(minutes) && minutes >= 0 ? minutes : 0;
    setIdleLogoutMinutesState(safe);
    window.localStorage.setItem(IDLE_MINUTES_KEY, String(safe));
  };

  useEffect(() => {
    if (!isAuthenticated || idleLogoutMinutes <= 0) {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      return;
    }

    const armTimeout = () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = window.setTimeout(() => {
        void logout("idle");
      }, idleLogoutMinutes * 60 * 1000);
    };

    const onActivity = () => armTimeout();

    armTimeout();
    window.addEventListener("mousemove", onActivity);
    window.addEventListener("keydown", onActivity);
    window.addEventListener("mousedown", onActivity);
    window.addEventListener("touchstart", onActivity);
    window.addEventListener("scroll", onActivity, true);

    return () => {
      window.removeEventListener("mousemove", onActivity);
      window.removeEventListener("keydown", onActivity);
      window.removeEventListener("mousedown", onActivity);
      window.removeEventListener("touchstart", onActivity);
      window.removeEventListener("scroll", onActivity, true);
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [idleLogoutMinutes, isAuthenticated]);

  const value = useMemo<AuthContextValue>(
    () => ({ isAuthenticated, logoutReason, idleLogoutMinutes, setIdleLogoutMinutes, login, logout }),
    [isAuthenticated, logoutReason, idleLogoutMinutes]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
