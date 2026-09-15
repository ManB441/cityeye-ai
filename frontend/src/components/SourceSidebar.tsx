import { useMemo, useState } from "react";
import type { ScenarioId, ScenarioInfo } from "../types";

export function SourceSidebar({ scenarios, selected, onSelect }: {
  scenarios: ScenarioInfo[];
  selected: ScenarioId;
  onSelect: (scenarioId: ScenarioId) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => scenarios.filter((scenario) => (
    `${scenario.title} ${scenario.description}`.toLowerCase().includes(query.toLowerCase())
  )), [query, scenarios]);
  return (
    <aside className="source-sidebar" aria-label="Video sources">
      <div className="sidebar-heading"><span>VIDEO SOURCES</span><b>{scenarios.length}</b></div>
      <label className="source-search"><span aria-hidden="true">⌕</span><input aria-label="Search sources" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sources" /></label>
      <section>
        <h2>LIVE CAMERAS</h2>
        <div className="source-empty"><i />No live cameras configured<small>RTSP source required</small></div>
      </section>
      <section>
        <h2>MUNICIPALITY DEMO FOOTAGE</h2>
        <div className="source-list">
          {filtered.map((scenario) => (
            <button key={scenario.scenario_id} type="button" className={scenario.scenario_id === selected ? "selected" : ""} onClick={() => onSelect(scenario.scenario_id)}>
              <span className="source-icon">▶</span>
              <span><strong>{scenario.title}</strong><small>Recorded test footage</small></span>
              <em>RECORDED</em>
            </button>
          ))}
          {filtered.length === 0 && <div className="source-empty">No matching source</div>}
        </div>
      </section>
    </aside>
  );
}
