import { useEffect, useMemo, useState } from "react";
import { fetchScenarioSnapshots } from "../api/analysis";
import type { ScenarioSnapshot } from "../types";
import { PageTitle } from "./CamerasPage";

export function AnalyticsPage() {
  const [snapshots, setSnapshots] = useState<ScenarioSnapshot[]>([]);
  const [loadError, setLoadError] = useState(false);
  useEffect(() => {
    void fetchScenarioSnapshots().then((items) => { setSnapshots(items); setLoadError(false); }).catch(() => setLoadError(true));
  }, []);
  const incomplete = loadError || snapshots.some(({ summaryError, eventsError }) => summaryError || eventsError);
  const real = useMemo(
    () => ({
      sources: snapshots.length,
      available: snapshots.filter(({ summary }) => summary?.status === "READY")
        .length,
      records: snapshots.reduce(
        (sum, { summary }) => sum + (summary?.total_track_records ?? 0),
        0,
      ),
      incidents: snapshots.reduce((sum, { events }) => sum + events.length, 0),
    }),
    [snapshots],
  );
  return (
    <main className="operations-page">
      <PageTitle
        label="TRAFFIC INTELLIGENCE"
        title="Analytics"
        copy="Current processed-dataset facts and clearly separated future analytics."
      />
      {incomplete && <div className="command-error" role="alert">Some current analytics are unavailable because one or more backend requests failed.</div>}
      <section className="analytics-summary">
        <article>
          <span>Configured recordings</span>
          <strong>{real.sources}</strong>
          <small>Real scenario API</small>
        </article>
        <article>
          <span>Available analyses</span>
          <strong>{incomplete ? "—" : real.available}</strong>
          <small>READY outputs</small>
        </article>
        <article>
          <span>Track records</span>
          <strong>{incomplete ? "—" : real.records}</strong>
          <small>Across current outputs</small>
        </article>
        <article>
          <span>Detected events</span>
          <strong>{incomplete ? "—" : real.incidents}</strong>
          <small>Stored scenario events</small>
        </article>
      </section>
      <section className="analytics-grid">
        <article className="future-panel wide">
          <div>
            <span>TRAFFIC HISTORY</span>
            <em>DATA COLLECTION REQUIRED</em>
          </div>
          <h2>Historical operational analytics</h2>
          <p>
            Traffic volume today, peak hour, congestion duration, camera uptime,
            and road-segment performance require timestamped historical
            aggregation that is not currently available.
          </p>
          <div className="chart-placeholder">
            <i />
            <i />
            <i />
            <i />
            <i />
            <span>Historical series will appear here</span>
          </div>
        </article>
        <article className="future-panel">
          <div>
            <span>CONGESTION PREDICTION</span>
            <em>FUTURE / DATA COLLECTION</em>
          </div>
          <h2>Forecasting inactive</h2>
          <p>
            No historical baseline store exists yet. Forecasting can activate
            only after timestamped traffic observations are persisted and
            retained long enough to establish reliable baselines.
          </p>
          <div className="future-icon">↗</div>
        </article>
        <article className="future-panel multi-camera">
          <div>
            <span>MULTI-CAMERA ANALYSIS</span>
            <em>CALIBRATION REQUIRED</em>
          </div>
          <h2>Road intelligence</h2>
          <p>
            Sequential cameras must be configured and calibrated before inflow,
            outflow, or accumulation can be measured.
          </p>
          <div className="road-model">
            <span>
              <b>CAM-01</b>
              <small>Beginning of road</small>
            </span>
            <i>→ ROAD SEGMENT →</i>
            <span>
              <b>CAM-02</b>
              <small>Next road segment</small>
            </span>
          </div>
        </article>
      </section>
    </main>
  );
}
