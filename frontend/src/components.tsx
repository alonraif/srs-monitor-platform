import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

const navItems = [
  { label: "Dashboard", to: "/" },
  { label: "Streams", to: "/streams" },
  { label: "Alarms", to: "/alarms" },
  { label: "Expected Streams", to: "/expected-streams" },
  { label: "Multiviewer", to: "/multiviewer" },
  { label: "Settings", to: "/settings" }
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">SRS Monitor</div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <section className="content">
        <header className="topbar">
          <div className="topbar-title">Network Operations</div>
          <div className="topbar-status">Auto-refresh: 5s</div>
        </header>
        <main className="page">{children}</main>
      </section>
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="state loading">
      <div className="skeleton-line w40"></div>
      <div className="skeleton-line"></div>
      <div className="skeleton-line w70"></div>
    </div>
  );
}

export function ErrorState({ error }: { error: string }) {
  return <div className="state error">Error: {error}</div>;
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state empty">{message}</div>;
}
