import { useEffect, useMemo, useState } from "react";
import { fetchScenarioSnapshots } from "../api/analysis";
import { evidenceUrl } from "../api/events";
import type { ScenarioSnapshot } from "../types";

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
  const [sources, setSources] = useState<ScenarioSnapshot[]>([]);
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
      <section className="honest-banner">
        <span>LIVE CAMERAS</span>
        <strong>Not yet available</strong>
        <p>
          No live RTSP camera is configured in this environment. Live sources
          will appear here only after backend configuration is available.
        </p>
      </section>
    </main>
  );
}
