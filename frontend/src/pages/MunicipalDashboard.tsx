import { dashboardFixture } from "../fixtures/dashboardFixture";

export function MunicipalDashboard() {
  const event = dashboardFixture.events[0];
  return (
    <main className="dashboard">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Municipal operations</p>
          <h1>Traffic Monitoring Dashboard</h1>
          <p>Local competition MVP · {dashboardFixture.cameraName}</p>
        </div>
        <div className="fixture-badge">FIXTURE DATA — NOT AI OUTPUT</div>
      </section>

      <section className="metric-grid" aria-label="Current traffic summary">
        <article className="metric-card"><span>Current vehicles</span><strong>{dashboardFixture.vehicleCount}</strong></article>
        <article className="metric-card"><span>Traffic status</span><strong>{dashboardFixture.trafficStatus}</strong></article>
        <article className="metric-card"><span>Open events</span><strong>{dashboardFixture.events.length}</strong></article>
      </section>

      <section className="dashboard-grid">
        <article className="panel video-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Processed video</p><h2>Camera analysis</h2></div>
            <span className="status-dot">Layout preview</span>
          </div>
          <div className="video-placeholder" role="img" aria-label="Processed video placeholder">
            <span>Annotated video will appear here after Backend integration</span>
          </div>
        </article>

        <article className="panel event-panel">
          <div className="panel-heading"><div><p className="eyebrow">Event queue</p><h2>Live events</h2></div></div>
          <div className="event-card">
            <div className="event-title-row">
              <strong>{event.eventType}</strong>
              <span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span>
            </div>
            <p>{event.explanation}</p>
            <dl>
              <div><dt>Confidence</dt><dd>{Math.round(event.confidence * 100)}%</dd></div>
              <div><dt>Timestamp</dt><dd>{event.timestamp}</dd></div>
            </dl>
            <div className="evidence-placeholder">Evidence JPG preview</div>
            <div className="event-actions">
              <button type="button" disabled>Verify</button>
              <button type="button" className="secondary" disabled>Dismiss</button>
            </div>
            <small>Buttons are disabled until Backend integration.</small>
          </div>
        </article>
      </section>
    </main>
  );
}
