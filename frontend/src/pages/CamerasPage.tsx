import { useEffect, useMemo, useState } from "react";
import "../live-camera.css";
import { fetchScenarioSnapshots } from "../api/analysis";
import { evidenceUrl } from "../api/events";
import { fetchLiveCameras, fetchLiveEvents, fetchLiveMetrics } from "../api/live";
import { LiveMjpegImage } from "../components/LiveMjpegImage";
import { cameraIsOnline, cameraStateLabel, currentLiveMetrics, trafficCondition, useFreshnessClock } from "../lib/liveTruth";
import type { CameraHealth, LiveMetricsSnapshot, ScenarioSnapshot } from "../types";

const LIVE_CAMERA_NAMES: Record<string, string> = {
  "camera-3": "DVR Camera 3",
  "camera-5": "DVR Camera 5",
  "camera-7": "DVR Camera 7",
};

type LiveCameraSnapshot = {
  health: CameraHealth;
  metrics: LiveMetricsSnapshot | null;
  incidentCount: number | null;
};

export function PageTitle({
  label,
  title,
  copy,
}: {
  label: string;
  title: string;
  copy: string;
}) {
  return (
    <header className="operations-title">
      <div>
        <span>{label}</span>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
    </header>
  );
}
export function CamerasPage() {
  const now = useFreshnessClock();
  const [sources, setSources] = useState<ScenarioSnapshot[]>([]);
  const [liveSources, setLiveSources] = useState<LiveCameraSnapshot[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<
    "ALL" | "ONLINE" | "OFFLINE" | "INCIDENTS"
  >("ALL");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void fetchScenarioSnapshots(controller.signal)
      .then((items) => { setSources(items); setLoadError(false); })
      .catch((error) => { if (!(error instanceof DOMException && error.name === "AbortError")) setLoadError(true); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);
  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    let controller: AbortController | null = null;
    async function refreshLiveSources() {
      if (inFlight) return;
      inFlight = true;
      controller = new AbortController();
      const signal = controller.signal;
      const timeout = window.setTimeout(() => controller?.abort(), 4_000);
      try {
        const cameras = await fetchLiveCameras(signal);
        const snapshots = await Promise.all(cameras.map(async (health) => {
          const [metrics, events] = await Promise.allSettled([
            fetchLiveMetrics(health.camera_id, signal),
            fetchLiveEvents(health.camera_id, signal),
          ]);
          return {
            health: metrics.status === "fulfilled" && metrics.value.health.camera_id === health.camera_id && metrics.value.health.checked_at >= health.checked_at ? metrics.value.health : health,
            metrics: metrics.status === "fulfilled" ? metrics.value : null,
            incidentCount: events.status === "fulfilled" ? events.value.events.filter((event) => event.status === "PROPOSED").length : null,
          };
        }));
        if (!cancelled) setLiveSources(snapshots);
      } catch {
        if (!cancelled) setLiveSources([]);
      } finally {
        window.clearTimeout(timeout);
        inFlight = false;
      }
    }
    void refreshLiveSources();
    const timer = window.setInterval(() => void refreshLiveSources(), 2_000);
    return () => { cancelled = true; controller?.abort(); window.clearInterval(timer); };
  }, []);
  const filtered = useMemo(
    () =>
      sources.filter(({ scenario, summary, events }) => {
        if (!scenario.title.toLowerCase().includes(query.toLowerCase()))
          return false;
        if (filter === "ONLINE") return summary?.status === "READY";
        if (filter === "OFFLINE") return summary?.status !== "READY";
        if (filter === "INCIDENTS")
          return events.some((event) => event.status === "PROPOSED");
        return true;
      }),
    [filter, query, sources],
  );
  const filteredLive = useMemo(() => liveSources.filter(({ health, incidentCount }) => {
    const name = LIVE_CAMERA_NAMES[health.camera_id] ?? health.camera_id;
    if (!name.toLowerCase().includes(query.toLowerCase())) return false;
    if (filter === "ONLINE") return cameraIsOnline(health, now);
    if (filter === "OFFLINE") return !cameraIsOnline(health, now);
    if (filter === "INCIDENTS") return (incidentCount ?? 0) > 0;
    return true;
  }), [filter, liveSources, query, now]);
  return (
    <main className="operations-page">
      <PageTitle
        label="SOURCE MANAGEMENT"
        title="Cameras & Video Sources"
        copy="Configured sources available to the current CityEye environment."
      />
      <section className="page-controls">
        <label>
          <span>⌕</span>
          <input
            aria-label="Search cameras"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by source or location"
          />
        </label>
        <div className="filter-tabs">
          {(["ALL", "ONLINE", "OFFLINE", "INCIDENTS"] as const).map((item) => (
            <button
              className={filter === item ? "active" : ""}
              onClick={() => setFilter(item)}
              key={item}
            >
              {item === "INCIDENTS" ? "WITH INCIDENTS" : item}
            </button>
          ))}
        </div>
        <div className="view-toggle">
          <button
            className={view === "grid" ? "active" : ""}
            onClick={() => setView("grid")}
          >
            ▦
          </button>
          <button
            className={view === "list" ? "active" : ""}
            onClick={() => setView("list")}
          >
            ☷
          </button>
        </div>
      </section>
      <div className="source-group-title">
        <span>LIVE CAMERAS</span>
        <b>{filteredLive.length}</b>
      </div>
      {filteredLive.length ? (
        <section className={`camera-collection ${view}`}>
          {filteredLive.map(({ health, metrics: snapshot, incidentCount }) => {
            const metrics = currentLiveMetrics(snapshot, health, health.camera_id, now);
            const online = cameraIsOnline(health, now);
            const state = cameraStateLabel(health, now);
            return (
            <article className="camera-card" key={health.camera_id}>
              <div className="camera-preview">
                {online ? <LiveMjpegImage
                  cameraId={health.camera_id}
                  alt={`Raw live preview for ${LIVE_CAMERA_NAMES[health.camera_id] ?? health.camera_id}`}
                /> : <div className="camera-preview-unavailable">Camera {state.toLowerCase()}</div>}
                <span>{state}</span>
                <em>Preview {online ? health.preview_publication_fps.toFixed(1) : "—"} FPS</em>
              </div>
              <div className="camera-body">
                <div>
                  <h2>{LIVE_CAMERA_NAMES[health.camera_id] ?? health.camera_id}</h2>
                  <span>Local DVR · YOLO + ByteTrack</span>
                </div>
                <span className={`camera-status ${online ? "online" : "offline"}`}>
                  <i />{state}
                </span>
                <dl>
                  <div><dt>Traffic state</dt><dd>{trafficCondition(metrics?.traffic_state)}</dd></div>
                  <div><dt>Current vehicles</dt><dd>{metrics?.active_vehicle_count ?? "—"}</dd></div>
                  <div><dt>Open incidents</dt><dd>{incidentCount ?? "—"}</dd></div>
                  <div><dt>Last frame</dt><dd>{metrics?.frame ?? "—"}</dd></div>
                  <div><dt>AI analysis</dt><dd>{metrics ? snapshot!.health.ai_inference_fps.toFixed(1) : "—"} FPS</dd></div>
                </dl>
              </div>
            </article>
          ); })}
        </section>
      ) : (
        <section className="honest-banner">
          <span>LIVE CAMERAS</span>
          <strong>No live cameras available</strong>
          <p>Start a configured camera worker to make its real processed feed available here.</p>
        </section>
      )}
      <div className="source-group-title">
        <span>MUNICIPALITY DEMO FOOTAGE</span>
        <b>{filtered.length}</b>
      </div>
      {loadError && <div className="command-error" role="alert">Configured sources are unavailable.</div>}
      {loading ? (
        <div className="page-empty">Loading configured sources…</div>
      ) : (
        <section className={`camera-collection ${view}`}>
          {filtered.map(({ scenario, summary, events, eventsError }, index) => (
            <article className="camera-card" key={scenario.scenario_id}>
              <div className="camera-preview">
                <video
                  muted
                  playsInline
                  preload="auto"
                  poster={events[0] ? evidenceUrl(events[0].evidence_image, scenario.scenario_id) : undefined}
                  src={`/media/scenarios/${scenario.scenario_id}/annotated.mp4#t=0.1`}
                />
                <span>RECORDED</span>
                <em>DEMO-{String(index + 1).padStart(2, "0")}</em>
              </div>
              <div className="camera-body">
                <div>
                  <h2>{scenario.title}</h2>
                  <span>Municipality test footage</span>
                </div>
                <span
                  className={`camera-status ${summary?.status === "READY" ? "online" : "offline"}`}
                >
                  <i />
                  {summary?.status === "READY" ? "AVAILABLE" : "UNAVAILABLE"}
                </span>
                <dl>
                  <div>
                    <dt>Traffic state</dt>
                    <dd>
                      {eventsError ? "Unavailable" : events.some(
                        (event) =>
                          event.event_type === "CONGESTION" &&
                          event.status !== "DISMISSED",
                      )
                        ? "Congested"
                        : "No active congestion"}
                    </dd>
                  </div>
                  <div>
                    <dt>Current vehicles</dt>
                    <dd>{summary?.current_vehicle_count ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Open incidents</dt>
                    <dd>
                      {eventsError ? "—" :
                        events.filter((event) => event.status === "PROPOSED")
                          .length
                      }
                    </dd>
                  </div>
                  <div>
                    <dt>Last frame</dt>
                    <dd>{summary?.last_frame ?? "—"}</dd>
                  </div>
                </dl>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
