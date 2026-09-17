import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { fetchSystemReadiness } from "./api/system";
import { AppHeader } from "./components/AppHeader";
import { useAuth } from "./hooks/useAuth";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CamerasPage } from "./pages/CamerasPage";
import { CitizenMapPage } from "./pages/CitizenMapPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { MunicipalDashboard } from "./pages/MunicipalDashboard";
import type { SystemReadiness } from "./types";

const navigation = [
  ["/command-center", "Command Center", "▦"],
  ["/cameras", "Cameras", "◉"],
  ["/incidents", "Incidents", "△"],
  ["/analytics", "Analytics", "⌁"],
  ["/citizen-map", "Citizen Map", "⌖"],
] as const;

export default function App() {
  const auth = useAuth();
  const [readiness, setReadiness] = useState<SystemReadiness>({ status: "unavailable" });
  useEffect(() => {
    const controller = new AbortController();
    void fetchSystemReadiness(controller.signal).then(setReadiness).catch(() => setReadiness({ status: "unavailable" }));
    return () => controller.abort();
  }, []);
  return <div className="command-app">
    <AppHeader auth={auth} readiness={readiness} />
    <nav className="command-nav" aria-label="Primary navigation">{navigation.map(([path, label, icon]) => <NavLink to={path} key={path}><span aria-hidden="true">{icon}</span>{label}</NavLink>)}</nav>
    <div className="route-stage"><Routes>
      <Route path="/command-center" element={<MunicipalDashboard auth={auth} />} />
      <Route path="/dashboard" element={<Navigate to="/command-center" replace />} />
      <Route path="/cameras" element={<CamerasPage />} />
      <Route path="/incidents" element={<IncidentsPage auth={auth} />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/citizen-map" element={<CitizenMapPage />} />
      <Route path="/map" element={<Navigate to="/citizen-map" replace />} />
      <Route path="*" element={<Navigate to="/command-center" replace />} />
    </Routes></div>
  </div>;
}
