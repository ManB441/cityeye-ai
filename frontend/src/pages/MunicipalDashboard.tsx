import { useEffect, useMemo, useRef, useState } from "react";
import { fetchScenarios } from "../api/analysis";
import { fetchLiveCameras, fetchLiveEvents, fetchLiveMetrics, liveEvidenceUrl, reviewLiveEvent } from "../api/live";
import { IncidentCard, IncidentDetail } from "../components/Incident";
import { LiveMjpegImage } from "../components/LiveMjpegImage";
import { SourceSidebar } from "../components/SourceSidebar";
import type { AuthState } from "../hooks/useAuth";
import { useAnalysis } from "../hooks/useAnalysis";
import { useEvents } from "../hooks/useEvents";
import type { AnalysisFrame, CameraHealth, LiveMetrics, ScenarioId, ScenarioInfo, TrafficEvent } from "../types";

const EMPTY_FRAME: AnalysisFrame = { frame: 0, timestamp_sec: 0, active_vehicle_count: 0, cars: 0, buses: 0, trucks: 0, motorcycles: 0, people: 0, people_in_road: 0, tracked_people: 0, bicycles: 0, bicycles_in_road: 0, tracked_bicycles: 0 };
const CAMERA_NAMES: Record<string, string> = { "camera-3": "DVR Camera 3", "camera-5": "DVR Camera 5", "camera-7": "DVR Camera 7" };

export function MunicipalDashboard({ auth }: { auth: AuthState }) {
  const [scenarioId, setScenarioId] = useState<ScenarioId>("normal_traffic");
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [selectedLiveCamera, setSelectedLiveCamera] = useState<string | null>(null);
  const [liveView, setLiveView] = useState<"live" | "ai">("live");
  const initializedLiveSource = useRef(false);
  const [liveCameras, setLiveCameras] = useState<CameraHealth[]>([]);
  const [liveMetrics, setLiveMetrics] = useState<LiveMetrics | null>(null);
  const [liveEvents, setLiveEvents] = useState<TrafficEvent[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [reviewingLiveId, setReviewingLiveId] = useState<string | null>(null);
  const [videoTime, setVideoTime] = useState(0);
  const [analysisStarted, setAnalysisStarted] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TrafficEvent | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const { events, loading, error, reviewingEventId, refresh, decide } = useEvents(scenarioId);
  const { summary, timeline, error: analysisError, refresh: refreshAnalysis } = useAnalysis(scenarioId);
  const liveMode = selectedLiveCamera !== null;
  const selectedHealth = liveCameras.find((camera) => camera.camera_id === selectedLiveCamera) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    void fetchScenarios(controller.signal).then((items) => { setScenarios(items); setScenarioError(null); }).catch((requestError) => { if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setScenarioError(requestError instanceof Error ? requestError.message : "Unable to load sources"); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refreshLive() {
      try {
        const cameras = await fetchLiveCameras();
        if (cancelled) return;
        setLiveCameras(cameras);
        if (!initializedLiveSource.current) {
          initializedLiveSource.current = true;
          if (cameras.length) setSelectedLiveCamera(cameras[0].camera_id);
        }
        if (selectedLiveCamera) {
          const [metrics, eventPayload] = await Promise.all([fetchLiveMetrics(selectedLiveCamera), fetchLiveEvents(selectedLiveCamera)]);
          if (!cancelled) { setLiveMetrics(metrics); setLiveEvents(eventPayload.events); setLiveError(null); }
        }
      } catch (requestError) {
        if (!cancelled) {
          setLiveMetrics(null);
          setLiveError(requestError instanceof Error ? requestError.message : "Unable to load live cameras");
        }
      }
    }
    void refreshLive();
    const timer = window.setInterval(() => void refreshLive(), 2_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selectedLiveCamera]);

  const currentFrame = useMemo(() => {
    if (!timeline?.frames.length) return EMPTY_FRAME;
    let selected = timeline.frames[0] ?? EMPTY_FRAME;
    for (const frame of timeline.frames) { if (frame.timestamp_sec > videoTime) break; selected = frame; }
    return selected;
  }, [timeline, videoTime]);
  const currentLiveMetrics = liveMetrics && selectedHealth
    && liveMetrics.generation === selectedHealth.generation ? liveMetrics : null;
  const displayedFrame: AnalysisFrame = liveMode && currentLiveMetrics ? {
    frame: currentLiveMetrics.frame, timestamp_sec: currentLiveMetrics.timestamp, active_vehicle_count: currentLiveMetrics.active_vehicle_count,
    cars: currentLiveMetrics.cars, buses: currentLiveMetrics.buses, trucks: currentLiveMetrics.trucks, motorcycles: currentLiveMetrics.motorcycles,
    people: currentLiveMetrics.people, bicycles: currentLiveMetrics.bicycles, people_in_road: 0, tracked_people: 0, bicycles_in_road: 0, tracked_bicycles: 0,
  } : currentFrame;
  const visibleEvents = liveMode ? liveEvents : events.filter((event) => analysisStarted && event.timestamp <= videoTime);
  const proposedCount = visibleEvents.filter((event) => event.status === "PROPOSED").length;
  const congested = liveMode ? liveMetrics?.traffic_state === "HEAVY_CONGESTION" : visibleEvents.some((event) => event.event_type === "CONGESTION" && event.status !== "DISMISSED");
  const trafficStatus = congested ? "Congested" : proposedCount ? "Attention" : "Normal";
  const selectedScenario = scenarios.find((scenario) => scenario.scenario_id === scenarioId);
  const cameraName = liveMode ? CAMERA_NAMES[selectedLiveCamera] ?? selectedLiveCamera : events[0]?.camera_name ?? selectedScenario?.title ?? "Loading source";
  const canReview = !auth.loading && !auth.error && (!auth.authRequired || auth.user?.role === "REVIEWER" || auth.user?.role === "ADMIN");

  function selectScenario(next: ScenarioId) { setSelectedLiveCamera(null); setScenarioId(next); setVideoTime(0); setAnalysisStarted(false); setSelectedEvent(null); setLiveError(null); }
  function selectLive(cameraId: string) { setSelectedLiveCamera(cameraId); setLiveView("live"); setSelectedEvent(null); setLiveMetrics(null); setLiveEvents([]); setLiveError(null); }
  async function decideOn(event: TrafficEvent, decision: "verify" | "dismiss") {
    if (liveMode && selectedLiveCamera) {
      setReviewingLiveId(event.event_id);
      try { const updated = await reviewLiveEvent(selectedLiveCamera, event.event_id, decision); setLiveEvents((current) => current.map((item) => item.event_id === updated.event_id ? updated : item)); setSelectedEvent(updated); }
      finally { setReviewingLiveId(null); }
      return;
    }
    await decide(event.event_id, decision);
    setSelectedEvent((current) => current?.event_id === event.event_id ? { ...current, status: decision === "verify" ? "VERIFIED" : "DISMISSED" } : current);
  }

  const combinedError = liveMode ? liveError : scenarioError ?? error ?? analysisError;
  return <div className="command-layout">
    <SourceSidebar scenarios={scenarios} selected={scenarioId} onSelect={selectScenario} liveCameras={liveCameras} selectedLiveCamera={selectedLiveCamera} onSelectLive={selectLive} />
    <main className="command-main">
      <section className="workspace-heading"><div><span className="section-label">COMMAND CENTER</span><h1>{cameraName}</h1><p>Municipal traffic monitoring workspace</p></div><div className="recording-badge"><i />{liveMode ? "LIVE" : "RECORDED"}<small>{liveMode ? `${selectedHealth?.state ?? "CONNECTING"} · Preview ${selectedHealth?.preview_publication_fps.toFixed(1) ?? "0.0"} FPS` : "Municipality Test Footage"}</small></div></section>
      {combinedError && <div className="command-error" role="alert"><span>{combinedError}</span><button onClick={() => { if (liveMode) setLiveError(null); else { void refresh(); void refreshAnalysis(); } }}>Retry</button></div>}
      <article className="feed-panel"><div className="feed-toolbar"><div><span>{liveMode ? liveView === "live" ? "RAW LIVE CAMERA PREVIEW" : "AI PROCESSED CAMERA FEED" : "PROCESSED CAMERA FEED"}</span><strong>{cameraName}</strong></div><div className="feed-toolbar-actions">{liveMode && <div className="live-view-toggle" aria-label="Live camera view"><button type="button" className={liveView === "live" ? "active" : ""} onClick={() => setLiveView("live")}>LIVE VIEW</button><button type="button" className={liveView === "ai" ? "active" : ""} onClick={() => setLiveView("ai")}>AI VIEW</button></div>}<span className={`feed-state ${(liveMode ? selectedHealth?.state === "ONLINE" : summary?.status === "READY") ? "ready" : "waiting"}`}>{liveMode ? selectedHealth?.state ?? "CONNECTING" : summary?.status ?? "CHECKING"}</span><time>{liveMode ? `Preview ${selectedHealth?.preview_publication_fps.toFixed(1) ?? "0.0"} · AI ${(selectedHealth?.ai_inference_fps || selectedHealth?.processing_fps || 0).toFixed(1)} FPS` : `${videoTime.toFixed(1)}s`}</time></div></div>
        {liveMode && selectedLiveCamera ? <div className="command-stream">{selectedHealth?.state === "ONLINE" ? <LiveMjpegImage key={`${selectedLiveCamera}-${liveView}`} cameraId={selectedLiveCamera} mode={liveView} className="command-video" alt={liveView === "live" ? `Raw live preview for ${cameraName}` : `AI processed view for ${cameraName}`} /> : <div className="command-video-placeholder"><span>{cameraName} is {selectedHealth?.state.toLowerCase() ?? "connecting"}; no stale frame is shown.</span></div>}</div> : summary?.annotated_video_available ? <video key={scenarioId} className="command-video" controls preload="metadata" src={`/media/scenarios/${scenarioId}/annotated.mp4`} onPlay={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }} onTimeUpdate={(event) => setVideoTime(event.currentTarget.currentTime)} onSeeked={(event) => { setAnalysisStarted(true); setVideoTime(event.currentTarget.currentTime); }} onEnded={(event) => setVideoTime(event.currentTarget.currentTime)}>Your browser does not support MP4 video.</video> : <div className="command-video-placeholder"><span>{summary?.message ?? "Checking real AI output files…"}</span></div>}
        <div className="feed-footer"><span>{liveMode ? liveView === "live" ? "Raw source preview · independent from AI FPS" : "Actual YOLO + ByteTrack output · runs at measured AI FPS" : "YOLO + ByteTrack annotated output"}</span><span>Frame {displayedFrame.frame || "—"}</span><span>{liveMode ? "Local DVR · server-side stream" : selectedScenario?.source_url === "user-provided" ? "User-provided clip" : "Licensed test footage"}</span></div></article>
      <section className="metric-strip" aria-label="Current traffic summary">{[["Vehicles", displayedFrame.active_vehicle_count], ["Cars", displayedFrame.cars], ["Buses", displayedFrame.buses], ["Trucks", displayedFrame.trucks], ["Motorcycles", displayedFrame.motorcycles], ["People", displayedFrame.people], ["Bicycles", displayedFrame.bicycles], ...(liveMode ? [["Tracks", currentLiveMetrics?.active_track_count ?? 0]] : [])].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}<article><span>Traffic status</span><strong className={`traffic-state ${trafficStatus.toLowerCase()}`}>{trafficStatus}</strong></article></section>
      <section className="data-note"><span>{liveMode ? "REAL LIVE CAMERA DATA" : "REAL VIDEO-SYNCED DATA"}</span><p>{liveMode ? "Frames, detections, tracks, and incidents update from the selected local DVR camera." : "Metrics update from the existing analysis timeline as recorded footage plays. Flow and queue trend are not available."}</p></section>
    </main>
    <aside className="incident-rail"><div className="rail-heading"><div><span>LIVE INCIDENTS</span><small>{liveMode ? "Real-time camera queue" : "Video-synchronized queue"}</small></div><b>{visibleEvents.length}</b></div>{!liveMode && loading && <div className="rail-empty">Loading incidents…</div>}{!liveMode && !loading && !analysisStarted && <div className="rail-empty"><i>▶</i><strong>Start recorded footage</strong><span>Incidents will appear at their real video timestamp.</span></div>}{liveMode && visibleEvents.length === 0 && <div className="rail-empty"><strong>No live incident</strong><span>The AI event queue is clear for this camera.</span></div>}{!liveMode && !loading && analysisStarted && visibleEvents.length === 0 && <div className="rail-empty"><strong>No incident at this time</strong><span>The AI event queue is clear for the current video position.</span></div>}<div className="rail-list">{visibleEvents.map((event) => <IncidentCard key={event.event_id} event={event} scenarioId={scenarioId} live={liveMode} canReview={canReview} reviewing={(liveMode ? reviewingLiveId : reviewingEventId) === event.event_id} onView={() => setSelectedEvent(event)} onDecision={(decision) => void decideOn(event, decision)} />)}</div></aside>
    {selectedEvent && <IncidentDetail event={selectedEvent} scenarioId={scenarioId} live={liveMode} evidenceSrc={liveMode && selectedLiveCamera ? liveEvidenceUrl(selectedLiveCamera, selectedEvent.evidence_image) : undefined} canReview={canReview} reviewing={(liveMode ? reviewingLiveId : reviewingEventId) === selectedEvent.event_id} onClose={() => setSelectedEvent(null)} onDecision={(decision) => void decideOn(selectedEvent, decision)} />}
  </div>;
}
