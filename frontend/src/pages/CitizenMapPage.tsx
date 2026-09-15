import { useEffect, useState } from "react";
import { fetchCitizenReports } from "../api/citizenReports";
import type { CitizenReport } from "../types";
import { PageTitle } from "./CamerasPage";

export function CitizenMapPage() {
  const [reports, setReports] = useState<CitizenReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetchCitizenReports(controller.signal)
      .then(setReports)
      .catch((requestError) => {
        if (!(
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ))
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Reports unavailable",
          );
      });
    return () => controller.abort();
  }, []);
  return (
    <main className="operations-page">
      <PageTitle
        label="PUBLIC TRAFFIC VIEW"
        title="Citizen Map"
        copy="Citizen report foundation with geographic visualization clearly marked as pending."
      />
      <section className="citizen-layout">
        <article className="map-placeholder">
          <div className="map-grid" />
          <div className="map-message">
            <span>MAP INTEGRATION</span>
            <strong>NOT YET AVAILABLE</strong>
            <p>
              No map provider is configured. Real report coordinates are not
              plotted until a geographic layer is implemented.
            </p>
          </div>
        </article>
        <aside className="report-panel">
          <div>
            <span>CITIZEN REPORTS</span>
            <b>{reports.length}</b>
          </div>
          {error && <p className="inline-error">{error}</p>}
          {reports.slice(0, 8).map((report) => (
            <article key={report.report_id}>
              <span className={`report-dot ${report.status.toLowerCase()}`} />
              <div>
                <strong>{report.category.replace(/_/g, " ")}</strong>
                <p>{report.description}</p>
                <small>
                  {report.status} · {report.latitude.toFixed(4)},{" "}
                  {report.longitude.toFixed(4)}
                </small>
              </div>
            </article>
          ))}
          {!error && reports.length === 0 && (
            <div className="page-empty">
              No citizen reports are currently stored.
            </div>
          )}
        </aside>
      </section>
      <section className="corroboration">
        <div>
          <span>Citizen Report</span>
          <b>+</b>
          <span>Camera AI Evidence</span>
          <b>=</b>
          <span>AI Corroborated</span>
        </div>
        <em>NOT YET AVAILABLE</em>
        <p>
          The data sources exist independently. Automatic geographic and
          temporal corroboration has not been implemented.
        </p>
      </section>
    </main>
  );
}
