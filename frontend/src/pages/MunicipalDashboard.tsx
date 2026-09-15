import { useEffect, useMemo, useState } from "react";
import { fetchScenarios } from "../api/analysis";
import { IncidentCard, IncidentDetail } from "../components/Incident";
import { SourceSidebar } from "../components/SourceSidebar";
import type { AuthState } from "../hooks/useAuth";
import { useAnalysis } from "../hooks/useAnalysis";
import { useEvents } from "../hooks/useEvents";
import type { AnalysisFrame, ScenarioId, ScenarioInfo, TrafficEvent } from "../types";

const EMPTY_FRAME: AnalysisFrame = { frame: 0, timestamp_sec: 0, active_vehicle_count: 0, cars: 0, buses: 0, trucks: 0, motorcycles: 0, people: 0, people_in_road: 0, tracked_people: 0, bicycles: 0, bicycles_in_road: 0, tracked_bicycles: 0 };

export function MunicipalDashboard({ auth }: { auth: AuthState }) {
  const [scenarioId, setScenarioId] = useState<ScenarioId>("normal_traffic");
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [videoTime, setVideoTime] = useState(0);
  const [analysisStarted, setAnalysisStarted] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TrafficEvent | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const { events, loading, error, reviewingEventId, refresh, decide } = useEvents(scenarioId);
  const { summary, timeline, error: analysisError, refresh: refreshAnalysis } = useAnalysis(scenarioId);
  useEffect(() => { const controller = new AbortController(); void fetchScenarios(controller.signal).then((items) => { setScenarios(items); setScenarioError(null); }).catch((requestError) => { if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setScenarioError(requestError instanceof Error ? requestError.message : "Unable to load sources"); }); return () => controller.abort(); }, []);
  const currentFrame = useMemo(() => { if (!timeline?.frames.length) return EMPTY_FRAME; let selected = EMPTY_FRAME; for (const frame of timeline.frames) { if (frame.timestamp_sec > videoTime) break; selected = frame; } return selected; }, [timeline, videoTime]);
  const visibleEvents = events.filter((event) => analysisStarted && event.timestamp <= videoTime);
  const proposedCount = visibleEvents.filter((event) => event.status === "PROPOSED").length;
  const congested = visibleEvents.some((event) => event.event_type === "CONGESTION" && event.status !== "DISMISSED");
  const trafficStatus = congested ? "Congested" : proposedCount ? "Attention" : "Normal";
  const selectedScenario = scenarios.find((scenario) => scenario.scenario_id === scenarioId);
  const cameraName = events[0]?.camera_name ?? selectedScenario?.title ?? "Loading source";
  const canReview = !auth.loading && !auth.error && (!auth.authRequired || auth.user?.role === "REVIEWER" || auth.user?.role === "ADMIN");
  function selectScenario(next: ScenarioId) { setScenarioId(next); setVideoTime(0); setAnalysisStarted(false); setSelectedEvent(null); }
  async function decideOn(event: TrafficEvent, decision: "verify" | "dismiss") { await decide(event.event_id, decision); setSelectedEvent((current) => current?.event_id === event.event_id ? { ...current, status: decision === "verify" ? "VERIFIED" : "DISMISSED" } : current); }
  const combinedError = scenarioError ?? error ?? analysisError;
  return <div className="command-layout">
    <SourceSidebar scenarios={scenarios} selected={scenarioId} onSelect={selectScenario} />
    <main className="command-main">
      <section className="workspace-heading"><div><span className="section-label">COMMAND CENTER</span><h1>{cameraName}</h1><p>Municipal traffic monitoring workspace</p></div><div className="recording-badge"><i />RECORDED<small>Municipality Test Footage</small></div></section>
      {combinedError && <div className="command-error" role="alert"><span>{combinedError}</span><button onClick={() => { void refresh(); void refreshAnalysis(); }}>Retry</button></div>}
      <article className="feed-panel"><div className="feed-toolbar"><div><span>PROCESSED CAMERA FEED</span><strong>{selectedScenario?.title ?? cameraName}</strong></div><div><span className={`feed-state ${summary?.status === "READY" ? "ready" : "waiting"}`}>{summary?.status ?? "CHECKING"}</span><time>{videoTime.toFixed(1)}s</time></div></div>
        {summary?.annotated_video_available ? <video key={scenarioId} className="command-video" controls preload="metadata" src={`/media/scenarios/${scenarioId}/annotated.mp4`} onPlay={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }} onTimeUpdate={(event) => setVideoTime(event.currentTarget.currentTime)} onSeeked={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }} onEnded={(event) => setVideoTime(event.currentTarget.currentTime)}>Your browser does not support MP4 video.</video> : <div className="command-video-placeholder"><span>{summary?.message ?? "Checking real AI output files…"}</span></div>}
        <div className="feed-footer"><span>YOLO + ByteTrack annotated output</span><span>Frame {timeline?.frames.length ? currentFrame.frame : "—"}</span><span>{selectedScenario?.source_url === "user-provided" ? "User-provided clip" : "Licensed test footage"}</span></div></article>
      <section className="metric-strip" aria-label="Current traffic summary">{[["Vehicles", currentFrame.active_vehicle_count], ["Cars", currentFrame.cars], ["Buses", currentFrame.buses], ["Trucks", currentFrame.trucks], ["Motorcycles", currentFrame.motorcycles], ["People", currentFrame.people], ["Bicycles", currentFrame.bicycles]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}<article><span>Traffic status</span><strong className={`traffic-state ${trafficStatus.toLowerCase()}`}>{trafficStatus}</strong></article></section>
      <section className="data-note"><span>REAL VIDEO-SYNCED DATA</span><p>Metrics update from the existing analysis timeline as recorded footage plays. Flow and queue trend are not available.</p></section>
    </main>
    <aside className="incident-rail"><div className="rail-heading"><div><span>LIVE INCIDENTS</span><small>Video-synchronized queue</small></div><b>{visibleEvents.length}</b></div>{loading && <div className="rail-empty">Loading incidents…</div>}{!loading && !analysisStarted && <div className="rail-empty"><i>▶</i><strong>Start recorded footage</strong><span>Incidents will appear at their real video timestamp.</span></div>}{!loading && analysisStarted && visibleEvents.length === 0 && <div className="rail-empty"><strong>No incident at this time</strong><span>The AI event queue is clear for the current video position.</span></div>}<div className="rail-list">{visibleEvents.map((event) => <IncidentCard key={event.event_id} event={event} scenarioId={scenarioId} canReview={canReview} reviewing={reviewingEventId === event.event_id} onView={() => setSelectedEvent(event)} onDecision={(decision) => void decideOn(event, decision)} />)}</div></aside>
    {selectedEvent && <IncidentDetail event={selectedEvent} scenarioId={scenarioId} canReview={canReview} reviewing={reviewingEventId === selectedEvent.event_id} onClose={() => setSelectedEvent(null)} onDecision={(decision) => void decideOn(selectedEvent, decision)} />}
  </div>;
}
