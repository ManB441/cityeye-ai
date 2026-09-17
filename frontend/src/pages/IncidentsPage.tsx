import { useEffect, useMemo, useState } from "react";
import { fetchScenarioSnapshots } from "../api/analysis";
import { reviewEvent } from "../api/events";
import { IncidentDetail } from "../components/Incident";
import type { AuthState } from "../hooks/useAuth";
import type { ScenarioId, ScenarioSnapshot, TrafficEvent } from "../types";
import { PageTitle } from "./CamerasPage";

type IncidentRow = { event: TrafficEvent; scenarioId: ScenarioId };
export function IncidentsPage({ auth }: { auth: AuthState }) {
  const [snapshots, setSnapshots] = useState<ScenarioSnapshot[]>([]);
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
      auth.user?.role === "REVIEWER" ||
      auth.user?.role === "ADMIN");
  useEffect(() => {
    void fetchScenarioSnapshots().then((items) => {
      setSnapshots(items);
      setError(items.some(({ eventsError }) => eventsError) ? "Some incident sources are unavailable." : null);
    }).catch(() => setError("Incident data is unavailable."));
  }, []);
  const incidents = useMemo(
    () =>
      snapshots
        .flatMap(({ scenario, events }) =>
          events.map((event) => ({ event, scenarioId: scenario.scenario_id })),
        )
        .filter(
          ({ event }) =>
            filter === "ALL" ||
            (filter === "HIGH"
              ? event.severity === "HIGH"
              : event.status === filter),
        )
        .sort((a, b) => b.event.timestamp - a.event.timestamp),
    [filter, snapshots],
  );
  async function decide(row: IncidentRow, decision: "verify" | "dismiss") {
    setReviewing(row.event.event_id);
    try {
      const event = await reviewEvent(
        row.event.event_id,
        decision,
        row.scenarioId,
      );
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
      setError(null);
    } catch {
      setError("The municipal decision could not be saved. Please retry.");
    } finally {
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
      {error && <div className="command-error" role="alert">{error}</div>}
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
                src={`/evidence/scenarios/${row.scenarioId}/${encodeURIComponent(row.event.evidence_image.split("/").pop() ?? "")}`}
                alt=""
              />
              <span>
                <strong>{row.event.event_type.replace(/_/g, " ")}</strong>
                <small>{row.event.explanation}</small>
              </span>
            </button>
            <span>{row.event.camera_name}</span>
            <time>{row.event.timestamp.toFixed(1)}s video time</time>
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
                  reviewing === row.event.event_id
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
                  reviewing === row.event.event_id
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
          canReview={canReview}
          reviewing={reviewing === selected.event.event_id}
          onClose={() => setSelected(null)}
          onDecision={(decision) => void decide(selected, decision)}
        />
      )}
    </main>
  );
}
