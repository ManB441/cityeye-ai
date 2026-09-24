import { cameraIsOnline, cameraStateLabel, useFreshnessClock } from "../lib/liveTruth";
import { useMemo, useState } from "react";
import type { CameraHealth, ScenarioId, ScenarioInfo } from "../types";

const CAMERA_NAMES: Record<string, string> = {
  "camera-3": "DVR Camera 3",
  "camera-5": "DVR Camera 5",
  "camera-7": "DVR Camera 7",
};

export function SourceSidebar({ scenarios, selected, onSelect, liveCameras, selectedLiveCamera, onSelectLive }: {
  scenarios: ScenarioInfo[];
  selected: ScenarioId;
  onSelect: (scenarioId: ScenarioId) => void;
  liveCameras: CameraHealth[];
  selectedLiveCamera: string | null;
  onSelectLive: (cameraId: string) => void;
}) {
  const now = useFreshnessClock();
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => scenarios.filter((scenario) => (
    `${scenario.title} ${scenario.description}`.toLowerCase().includes(query.toLowerCase())
  )), [query, scenarios]);
  return (
    <aside className="source-sidebar" aria-label="Video sources">
      <div className="sidebar-heading"><span>VIDEO SOURCES</span><b>{scenarios.length + liveCameras.length}</b></div>
      <label className="source-search"><span aria-hidden="true">⌕</span><input aria-label="Search sources" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search sources" /></label>
      <section>
        <h2>LIVE CAMERAS</h2>
        {liveCameras.length ? <div className="source-list">
          {liveCameras.map((camera) => (
            <button key={camera.camera_id} type="button" className={camera.camera_id === selectedLiveCamera ? "selected" : ""} onClick={() => onSelectLive(camera.camera_id)}>
              <span className="source-icon">●</span>
              <span><strong>{CAMERA_NAMES[camera.camera_id] ?? camera.camera_id}</strong><small>Real DVR feed · {cameraIsOnline(camera, now) ? camera.camera_capture_fps.toFixed(1) : "—"} capture FPS</small></span>
              <em className={cameraIsOnline(camera, now) ? "online" : ""}>{cameraStateLabel(camera, now)}</em>
            </button>
          ))}
        </div> : <div className="source-empty"><i />No live cameras configured<small>RTSP source required</small></div>}
      </section>
      <section>
        <h2>MUNICIPALITY DEMO FOOTAGE</h2>
        <div className="source-list">
          {filtered.map((scenario) => (
            <button key={scenario.scenario_id} type="button" className={selectedLiveCamera === null && scenario.scenario_id === selected ? "selected" : ""} onClick={() => onSelect(scenario.scenario_id)}>
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
