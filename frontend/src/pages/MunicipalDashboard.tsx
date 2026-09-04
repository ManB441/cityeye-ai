import { useEffect, useMemo, useState } from "react";
import { evidenceUrl } from "../api/events";
import { fetchScenarios } from "../api/analysis";
import { useEvents } from "../hooks/useEvents";
import { useAnalysis } from "../hooks/useAnalysis";
import type { AnalysisFrame, ScenarioId, ScenarioInfo, TrafficEvent } from "../types";

const EMPTY_FRAME: AnalysisFrame = {
  frame: 0, timestamp_sec: 0, active_vehicle_count: 0,
  cars: 0, buses: 0, trucks: 0, motorcycles: 0,
};

function EventCard({ event, reviewing, onDecision, scenarioId }: {
  event: TrafficEvent;
  reviewing: boolean;
  onDecision: (decision: "verify" | "dismiss") => void;
  scenarioId: ScenarioId;
}) {
  const proposed = event.status === "PROPOSED";
  return (
    <div className="event-card">
      <div className="event-title-row">
        <div>
          <span className="event-kicker">AI traffic event</span>
          <strong>{event.event_type}</strong>
        </div>
        <span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span>
      </div>
      <p>{event.explanation}</p>
      <dl>
        <div><dt>Status</dt><dd>{event.status}</dd></div>
        <div><dt>Confidence</dt><dd>{Math.round(event.confidence * 100)}%</dd></div>
        <div><dt>Video time</dt><dd>{event.timestamp.toFixed(1)}s</dd></div>
        <div><dt>Camera</dt><dd>{event.camera_name}</dd></div>
      </dl>
      <img className="evidence-image" src={evidenceUrl(event.evidence_image, scenarioId)} alt={`Evidence for ${event.event_type}`} />
      <div className="event-actions">
        <button type="button" disabled={!proposed || reviewing} onClick={() => onDecision("verify")}>Verify</button>
        <button type="button" className="secondary" disabled={!proposed || reviewing} onClick={() => onDecision("dismiss")}>Dismiss</button>
      </div>
      {!proposed && <small>Municipal decision recorded: {event.status}</small>}
    </div>
  );
}

export function MunicipalDashboard() {
  const [scenarioId, setScenarioId] = useState<ScenarioId>("normal_traffic");
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const { events, loading, error, reviewingEventId, refresh, decide } = useEvents(scenarioId);
  const { summary, timeline, error: analysisError, refresh: refreshAnalysis } = useAnalysis(scenarioId);
  const [videoTime, setVideoTime] = useState(0);
  const [analysisStarted, setAnalysisStarted] = useState(false);
  const currentFrame = useMemo(() => {
    if (!analysisStarted || !timeline?.frames.length) return EMPTY_FRAME;
    let selected = EMPTY_FRAME;
    for (const frame of timeline.frames) {
      if (frame.timestamp_sec > videoTime) break;
      selected = frame;
    }
    return selected;
  }, [analysisStarted, timeline, videoTime]);
  const visibleEvents = events.filter((event) => analysisStarted && event.timestamp <= videoTime);
  const proposedCount = visibleEvents.filter((event) => event.status === "PROPOSED").length;
  const hasCongestion = visibleEvents.some((event) => event.event_type === "CONGESTION" && event.status !== "DISMISSED");
  const trafficStatus = hasCongestion ? "Congested" : proposedCount > 0 ? "Attention" : "Normal";
  const selectedScenario = scenarios.find((scenario) => scenario.scenario_id === scenarioId);
  const cameraName = events[0]?.camera_name ?? selectedScenario?.title ?? "Loading camera";
  const systemActive = summary?.status === "READY";

  useEffect(() => {
    const controller = new AbortController();
    void fetchScenarios(controller.signal).then(setScenarios);
    return () => controller.abort();
  }, []);

  function selectScenario(next: ScenarioId) {
    setScenarioId(next);
    setVideoTime(0);
    setAnalysisStarted(false);
  }

  return (
    <main className="dashboard">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Municipal operations</p>
          <h1>Traffic Monitoring Dashboard</h1>
          <p className="heading-subtitle">Operational view · {cameraName}</p>
        </div>
        <div className={`system-badge ${systemActive ? "active" : "waiting"}`}>
          <span aria-hidden="true" />
          {systemActive ? "AI System Active" : "Checking AI System"}
        </div>
      </section>

      {(error || analysisError) && <div className="error-banner" role="alert"><span>{error ?? analysisError}</span><button type="button" onClick={() => { void refresh(); void refreshAnalysis(); }}>Retry</button></div>}

      <section className="monitoring-grid" aria-label="AI traffic monitoring">
        <article className="panel video-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Processed camera feed</p>
              <h2>Camera Analysis</h2>
              <span className="camera-label">{cameraName}</span>
            </div>
            <div className="video-status">
              <span className="status-dot">{summary?.status ?? "Loading"}</span>
              <span className="video-clock">{videoTime.toFixed(1)}s</span>
            </div>
          </div>
          {summary?.annotated_video_available ? (
            <video key={scenarioId} className="processed-video" controls preload="metadata" src={`/media/scenarios/${scenarioId}/annotated.mp4`}
              onPlay={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }}
              onTimeUpdate={(event) => setVideoTime(event.currentTarget.currentTime)}
              onSeeked={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }}
              onEnded={(event) => setVideoTime(event.currentTarget.currentTime)}>
              Your browser does not support MP4 video.
            </video>
          ) : (
            <div className="video-placeholder" role="img" aria-label="Processed video unavailable">
              <span>{summary?.message ?? "Checking real AI output files…"}</span>
            </div>
          )}
          {selectedScenario && <p className="source-credit">Video source: <a href={selectedScenario.source_url} target="_blank" rel="noreferrer">Pexels · free-to-use source</a></p>}
        </article>

        <article className="panel event-panel">
          <div className="panel-heading event-panel-heading">
            <div><p className="eyebrow">Event queue</p><h2>Live Events</h2></div>
            <span className="event-count">{visibleEvents.length}</span>
          </div>
          {loading && <div className="state-card">Loading events…</div>}
          {!loading && !analysisStarted && <div className="state-card">Press Play to synchronize real tracking data and events.</div>}
          {!loading && analysisStarted && visibleEvents.length === 0 && <div className="state-card">No AI event has occurred at this video time.</div>}
          <div className="event-list">
            {visibleEvents.map((event) => <EventCard key={event.event_id} event={event} scenarioId={scenarioId} reviewing={reviewingEventId === event.event_id} onDecision={(decision) => void decide(event.event_id, decision)} />)}
          </div>
        </article>
      </section>

      <section className="metric-grid" aria-label="Current traffic summary">
        <article className="metric-card primary-metric"><span>Active tracked</span><strong>{currentFrame.active_vehicle_count}</strong></article>
        <article className="metric-card"><span>Cars</span><strong>{currentFrame.cars}</strong></article>
        <article className="metric-card"><span>Buses</span><strong>{currentFrame.buses}</strong></article>
        <article className="metric-card"><span>Trucks</span><strong>{currentFrame.trucks}</strong></article>
        <article className="metric-card"><span>Motorcycles</span><strong>{currentFrame.motorcycles}</strong></article>
        <article className="metric-card traffic-metric"><span>Traffic status</span><strong className={`traffic-pill ${trafficStatus.toLowerCase()}`}>{trafficStatus}</strong></article>
        <article className="metric-card"><span>Proposed events</span><strong>{proposedCount}</strong></article>
        <article className="metric-card"><span>Video position</span><strong>{videoTime.toFixed(1)}s</strong></article>
      </section>

      <section className="scenario-section">
        <div className="section-heading">
          <div><p className="eyebrow">Demonstration feeds</p><h2>Choose Traffic Scenario</h2></div>
          <span>Real precomputed AI output · video-synced</span>
        </div>
        <div className="scenario-grid" aria-label="Traffic demonstration scenarios">
          {scenarios.map((scenario) => (
            <button key={scenario.scenario_id} type="button"
              className={`scenario-card ${scenario.scenario_id === scenarioId ? "selected" : ""}`}
              onClick={() => selectScenario(scenario.scenario_id)}>
              <span>Scenario</span><strong>{scenario.title}</strong><small>{scenario.description}</small>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
