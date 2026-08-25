import { evidenceUrl } from "../api/events";
import { useEvents } from "../hooks/useEvents";
import type { TrafficEvent } from "../types";

function EventCard({ event, reviewing, onDecision }: {
  event: TrafficEvent;
  reviewing: boolean;
  onDecision: (decision: "verify" | "dismiss") => void;
}) {
  const proposed = event.status === "PROPOSED";
  return (
    <div className="event-card">
      <div className="event-title-row">
        <strong>{event.event_type}</strong>
        <span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span>
      </div>
      <p>{event.explanation}</p>
      <dl>
        <div><dt>Status</dt><dd>{event.status}</dd></div>
        <div><dt>Confidence</dt><dd>{Math.round(event.confidence * 100)}%</dd></div>
        <div><dt>Video time</dt><dd>{event.timestamp.toFixed(1)}s</dd></div>
        <div><dt>Camera</dt><dd>{event.camera_name}</dd></div>
      </dl>
      <img className="evidence-image" src={evidenceUrl(event.evidence_image)} alt={`Evidence for ${event.event_type}`} />
      <div className="event-actions">
        <button type="button" disabled={!proposed || reviewing} onClick={() => onDecision("verify")}>Verify</button>
        <button type="button" className="secondary" disabled={!proposed || reviewing} onClick={() => onDecision("dismiss")}>Dismiss</button>
      </div>
      {!proposed && <small>Municipal decision recorded: {event.status}</small>}
    </div>
  );
}

export function MunicipalDashboard() {
  const { events, loading, error, reviewingEventId, refresh, decide } = useEvents();
  const proposedCount = events.filter((event) => event.status === "PROPOSED").length;
  const hasCongestion = events.some((event) => event.event_type === "CONGESTION" && event.status !== "DISMISSED");
  const trafficStatus = hasCongestion ? "Congested" : proposedCount > 0 ? "Attention" : "Normal";
  const cameraName = events[0]?.camera_name ?? "No active camera event";

  return (
    <main className="dashboard">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Municipal operations</p>
          <h1>Traffic Monitoring Dashboard</h1>
          <p>Local competition MVP · {cameraName}</p>
        </div>
        <div className="live-badge">LIVE BACKEND DATA · 2s POLLING</div>
      </section>

      {error && <div className="error-banner" role="alert"><span>{error}</span><button type="button" onClick={() => void refresh()}>Retry</button></div>}

      <section className="metric-grid" aria-label="Current traffic summary">
        <article className="metric-card"><span>Current vehicles</span><strong>Unavailable</strong></article>
        <article className="metric-card"><span>Traffic status</span><strong>{trafficStatus}</strong></article>
        <article className="metric-card"><span>Proposed events</span><strong>{proposedCount}</strong></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel video-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Processed video</p><h2>Camera analysis</h2></div>
            <span className="status-dot">Pending media endpoint</span>
          </div>
          <div className="video-placeholder" role="img" aria-label="Processed video placeholder">
            <span>Annotated video integration is a separate task. No simulated stream is shown.</span>
          </div>
        </article>

        <article className="panel event-panel">
          <div className="panel-heading"><div><p className="eyebrow">Event queue</p><h2>Live events</h2></div><span>{events.length}</span></div>
          {loading && <div className="state-card">Loading events…</div>}
          {!loading && events.length === 0 && <div className="state-card">No AI events have been stored yet.</div>}
          <div className="event-list">
            {events.map((event) => <EventCard key={event.event_id} event={event} reviewing={reviewingEventId === event.event_id} onDecision={(decision) => void decide(event.event_id, decision)} />)}
          </div>
        </article>
      </section>
    </main>
  );
}
