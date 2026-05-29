import { FormEvent, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { AppShell } from "./components";
import {
  AlarmsPage,
  DashboardPage,
  ExpectedStreamsPage,
  MultiviewerPage,
  PenaltyBoxPage,
  SettingsPage,
  StreamDetailPage,
  StreamsPage
} from "./pages";

export default function App() {
  const { isAuthenticated, logoutReason, login, logout } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setError("");
    const ok = await login(password);
    if (!ok) {
      setError("Invalid password");
    } else {
      setPassword("");
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={onLogin}>
          <div className="login-brand">
            <img
              className="login-brand-logo"
              src="https://cdn-liveutv.pressidium.com/wp-content/uploads/2024/01/Live-and-Ulimted-all-white-V2.png"
              alt="Live and Unlimited"
            />
            <h1 className="login-title">SRS monitor</h1>
          </div>
          <h2>Login</h2>
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          {error ? <div className="login-error">{error}</div> : null}
          {logoutReason === "idle" ? <div className="login-info">You were logged out due to inactivity.</div> : null}
          <button type="submit">Sign In</button>
        </form>
      </div>
    );
  }

  return (
    <AppShell onLogout={() => void logout()}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/streams" element={<StreamsPage />} />
        <Route path="/streams/:id" element={<StreamDetailPage />} />
        <Route path="/alarms" element={<AlarmsPage />} />
        <Route path="/expected-streams" element={<ExpectedStreamsPage />} />
        <Route path="/multiviewer" element={<MultiviewerPage />} />
        <Route path="/penalty-box" element={<PenaltyBoxPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
