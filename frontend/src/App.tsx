import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components";
import {
  AlarmsPage,
  DashboardPage,
  ExpectedStreamsPage,
  MultiviewerPage,
  SettingsPage,
  StreamDetailPage,
  StreamsPage
} from "./pages";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/streams" element={<StreamsPage />} />
        <Route path="/streams/:id" element={<StreamDetailPage />} />
        <Route path="/alarms" element={<AlarmsPage />} />
        <Route path="/expected-streams" element={<ExpectedStreamsPage />} />
        <Route path="/multiviewer" element={<MultiviewerPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
