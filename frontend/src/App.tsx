import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { fetchSystemReadiness } from "./api/system";
import { AppHeader } from "./components/AppHeader";
import { useAuth } from "./hooks/useAuth";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CamerasPage } from "./pages/CamerasPage";
import { CitizenMapPage } from "./pages/CitizenMapPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { MunicipalDashboard } from "./pages/MunicipalDashboard";
import { LoginPage } from "./pages/LoginPage";
import { UsersPage, AccessRestricted } from "./pages/UsersPage";
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
  const location = useLocation();
  const citizen = auth.user?.role === "CITIZEN";
  const home = citizen ? "/citizen-map" : "/command-center";
  const [readiness, setReadiness] = useState<SystemReadiness>({ status: "unavailable" });
  useEffect(() => {
    if (!auth.initialized || (auth.authRequired && !auth.user) || citizen) return;
    const controller = new AbortController();
    void fetchSystemReadiness(controller.signal).then(setReadiness).catch(() => setReadiness({ status: "unavailable" }));
    return () => controller.abort();
  }, [auth.initialized, auth.authRequired, auth.user?.role, citizen]);
  if (!auth.initialized) return <div className="auth-bootstrap" role="status"><span>CE</span><p>Securing CityEye access…</p></div>;
  if (location.pathname === "/login") return <Routes><Route path="/login" element={<LoginPage auth={auth} />} /></Routes>;
  if (auth.authRequired && !auth.user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (citizen && !["/citizen-map", "/map"].includes(location.pathname)) return <Navigate to={home} replace />;
  return <div className="command-app">
    <AppHeader auth={auth} readiness={readiness} />
    <nav className="command-nav" aria-label="Primary navigation">{navigation.filter(([path]) => !citizen || path === "/citizen-map").map(([path, label, icon]) => <NavLink to={path} key={path}><span aria-hidden="true">{icon}</span>{label}</NavLink>)}{auth.user?.role === "ADMIN" && <NavLink to="/users"><span aria-hidden="true">◇</span>User access</NavLink>}</nav>
    <div className="route-stage"><Routes>
      <Route path="/command-center" element={<MunicipalDashboard auth={auth} />} />
      <Route path="/dashboard" element={<Navigate to="/command-center" replace />} />
      <Route path="/cameras" element={<CamerasPage />} />
      <Route path="/incidents" element={<IncidentsPage auth={auth} />} />
      <Route path="/users" element={auth.user?.role === "ADMIN" ? <UsersPage /> : <AccessRestricted />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/citizen-map" element={<CitizenMapPage key={`${auth.user?.user_id}:${auth.user?.role}`} />} />
      <Route path="/map" element={<Navigate to="/citizen-map" replace />} />
      <Route path="*" element={<Navigate to="/command-center" replace />} />
    </Routes></div>
  </div>;
}
