import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { MunicipalDashboard } from "./pages/MunicipalDashboard";

function CitizenMapPlaceholder() {
  return (
    <main className="placeholder-page">
      <p className="eyebrow">Citizen view</p>
      <h1>Citizen Traffic Map</h1>
      <p>The Leaflet map is not implemented in this task.</p>
    </main>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink className="brand" to="/dashboard">
          <span className="brand-mark">CE</span>
          <span>CityEye AI</span>
        </NavLink>
        <nav aria-label="Primary navigation">
          <NavLink to="/dashboard">Municipal Dashboard</NavLink>
          <NavLink to="/map">Citizen Map</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/dashboard" element={<MunicipalDashboard />} />
        <Route path="/map" element={<CitizenMapPlaceholder />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </div>
  );
}
