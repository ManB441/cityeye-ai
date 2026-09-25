import { useEffect, useMemo, useRef, useState } from "react";
import { fetchScenarioSnapshots } from "../api/analysis";
import { evidenceUrl, fetchPersistentEvents, liveIncidentEvidenceUrl, reviewEvent, reviewPersistentEvent } from "../api/events";
import { IncidentDetail } from "../components/Incident";
import type { AuthState } from "../hooks/useAuth";
import type { ScenarioId, ScenarioSnapshot, TrafficEvent } from "../types";
import { PageTitle } from "./CamerasPage";

type IncidentRow = { event: TrafficEvent; scenarioId?: ScenarioId };
export function IncidentsPage({ auth }: { auth: AuthState }) {
  const [snapshots, setSnapshots] = useState<ScenarioSnapshot[]>([]);
  const [liveEvents, setLiveEvents] = useState<TrafficEvent[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [pageLoading, setPageLoading] = useState(true);
  const [liveError, setLiveError] = useState<string | null>(null);
  const reviewVersion = useRef(0);
  const pendingReview = useRef(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [filter, setFilter] = useState<
    "ALL" | "PROPOSED" | "VERIFIED" | "DISMISSED" | "HIGH"
  >("ALL");
  const [selected, setSelected] = useState<IncidentRow | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canReview =
    !auth.loading &&
    !auth.error &&
    (!auth.authRequired ||
      auth.user?.role === "EMPLOYEE" ||
      auth.user?.role === "ADMIN");
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      const version = reviewVersion.current;
      try {
        const items = await fetchScenarioSnapshots(controller.signal);
        if (controller.signal.aborted || version !== reviewVersion.current) return;
        // Retain known incidents when a source is temporarily unavailable.
        setSnapshots(previous => items.map(item => item.eventsError
          ? { ...item, events: previous.find(old => old.scenario.scenario_id === item.scenario.scenario_id)?.events ?? [] }
          : item));
        setSelected(current => {
          if (!current?.scenarioId) return current;
          const event = items.find(item => item.scenario.scenario_id === current.scenarioId)?.events
            .find(item => item.event_id === current.event.event_id);
          return event ? { ...current, event } : current;
        });
        setError(items.some(({ eventsError }) => eventsError) ? "Some incident sources are unavailable." : null);
      } catch {
        if (!controller.signal.aborted && version === reviewVersion.current) setError("Incident data is unavailable.");
      } finally { inFlight = false; }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLiveEvents([]);
    setNextCursor(null);
    setPageLoading(true);
    let inFlight = false;
    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      const version = reviewVersion.current;
      try {
        const result = await fetchPersistentEvents(controller.signal, historyCursor);
        if (controller.signal.aborted || version !== reviewVersion.current) return;
        const items = result.events.filter((event) => event.source_type === "LIVE_CAMERA");
        setLiveEvents(items);
        setNextCursor(result.next_cursor ?? null);
        setHistoryTotal(result.total);
        setSelected((current) => current && !current.scenarioId
          ? { ...current, event: items.find((event) => event.event_id === current.event.event_id) ?? current.event }
          : current);
        setLiveError(null);
      } catch {
        if (!controller.signal.aborted && version === reviewVersion.current) setLiveError("Live incidents are unavailable. Recorded demos remain available.");
      } finally { inFlight = false; if (!controller.signal.aborted) setPageLoading(false); }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [historyCursor]);

  const incidents = useMemo(
    () =>
      [
        ...liveEvents.map((event): IncidentRow => ({ event })),
        ...snapshots.flatMap(({ scenario, events }) =>
          events.map((event): IncidentRow => ({ event, scenarioId: scenario.scenario_id })),
        ),
      ].filter((row, index, rows) => rows.findIndex((other) => other.event.event_id === row.event.event_id) === index)
        .filter(
          ({ event }) =>
            filter === "ALL" ||
            (filter === "HIGH"
              ? event.severity === "HIGH"
              : event.status === filter),
        )
        .sort((a, b) => b.event.timestamp - a.event.timestamp),
    [filter, snapshots, liveEvents],
  );
  async function decide(row: IncidentRow, decision: "verify" | "dismiss") {
    if (pendingReview.current) return;
    pendingReview.current = true;
    setReviewError(null);
    reviewVersion.current += 1;
    setReviewing(row.event.event_id);
    try {
      const event = row.scenarioId
        ? await reviewEvent(row.event.event_id, decision, row.scenarioId)
        : await reviewPersistentEvent(row.event.event_id, decision);
      reviewVersion.current += 1;
      setLiveEvents((current) => current.map((item) => item.event_id === event.event_id ? event : item));
      setSnapshots((current) =>
        current.map((snapshot) =>
          snapshot.scenario.scenario_id === row.scenarioId
            ? {
                ...snapshot,
                events: snapshot.events.map((item) =>
                  item.event_id === event.event_id ? event : item,
                ),
              }
            : snapshot,
        ),
      );
      setSelected((current) =>
        current?.event.event_id === event.event_id
          ? { ...current, event }
          : current,
      );
      setReviewError(null);
    } catch {
      setReviewError("The municipal decision could not be saved. Please retry.");
    } finally {
      pendingReview.current = false;
      setReviewing(null);
    }
  }
  return (
    <main className="operations-page">
      <PageTitle
        label="MUNICIPAL REVIEW"
        title="Incidents"
        copy="AI-proposed traffic events awaiting or carrying a municipal decision."
      />
      {reviewError && <div className="command-error" role="alert">{reviewError}</div>}
      {error && <div className="command-error" role="alert">{error}</div>}
      {liveError && <div className="command-error" role="alert">{liveError}</div>}
      <div className="filter-tabs" aria-label="Live history pages">
        <span>{pageLoading ? "Loading live history…" : `${liveEvents.length} live events on this page · ${historyTotal} in history`}</span>
        <button disabled={!historyCursor || pageLoading || reviewing !== null} onClick={() => { setSelected(null); setHistoryCursor(null); }}>Latest live events</button>
        <button disabled={!nextCursor || pageLoading || reviewing !== null} onClick={() => { setSelected(null); setHistoryCursor(nextCursor); }}>Older live events</button>
      </div>
      <p>Filters apply to this live page and the recorded demos below. Return to the latest page to see new live events.</p>
      <div className="filter-tabs incident-filters">
        {(["ALL", "PROPOSED", "VERIFIED", "DISMISSED", "HIGH"] as const).map(
          (item) => (
            <button
              key={item}
              className={filter === item ? "active" : ""}
              onClick={() => setFilter(item)}
            >
              {item === "PROPOSED"
                ? "NEW"
                : item === "HIGH"
                  ? "HIGH PRIORITY"
                  : item}
            </button>
          ),
        )}
      </div>
      <section className="incident-table" aria-label="Operational incidents">
        <div className="incident-table-head">
          <span>EVENT / EVIDENCE</span>
          <span>SOURCE</span>
          <span>DETECTED</span>
          <span>STATUS</span>
          <span>OPERATOR ACTION</span>
        </div>
        {incidents.map((row) => (
          <article key={`${row.scenarioId}-${row.event.event_id}`}>
            <button className="evidence-thumb" onClick={() => setSelected(row)}>
              <img
                src={row.scenarioId ? evidenceUrl(row.event.evidence_image, row.scenarioId) : liveIncidentEvidenceUrl(row.event)}
                alt=""
              />
              <span>
                <strong>{row.event.event_type.replace(/_/g, " ")}</strong>
                <small>{row.event.explanation}</small>
              </span>
            </button>
            <span>{row.scenarioId ? "RECORDED DEMO" : "LIVE"} · {row.event.camera_name}</span>
            <time>{row.scenarioId ? `${row.event.timestamp.toFixed(1)}s video time` : new Date(row.event.timestamp * 1000).toLocaleString()}</time>
            <span className={`review-status ${row.event.status.toLowerCase()}`}>
              {row.event.status}
            </span>
            <div className="table-actions">
              <button className="ghost" onClick={() => setSelected(row)}>
                View
              </button>
              <button
                disabled={
                  row.event.status !== "PROPOSED" ||
                  !canReview ||
                  reviewing !== null
                }
                onClick={() => void decide(row, "verify")}
              >
                Verify
              </button>
              <button
                className="danger-ghost"
                disabled={
                  row.event.status !== "PROPOSED" ||
                  !canReview ||
                  reviewing !== null
                }
                onClick={() => void decide(row, "dismiss")}
              >
                Dismiss
              </button>
            </div>
          </article>
        ))}
        {incidents.length === 0 && (
          <div className="page-empty">No real incidents match this filter.</div>
        )}
      </section>
      {selected && (
        <IncidentDetail
          event={selected.event}
          scenarioId={selected.scenarioId}
          live={!selected.scenarioId}
          evidenceSrc={selected.scenarioId ? undefined : liveIncidentEvidenceUrl(selected.event)}
          canReview={canReview}
          reviewing={reviewing !== null}
          onClose={() => setSelected(null)}
          onDecision={(decision) => void decide(selected, decision)}
        />
      )}
    </main>
  );
}
