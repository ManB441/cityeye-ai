import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/auth";
import { JourneyMap } from "../maps/JourneyMap";
import { expireFeatures, featureColor, type MapKind, type MapSnapshot } from "../maps/model";
import { PageTitle } from "./CamerasPage";

const LAYERS: [MapKind, string][] = [["road", "Road conditions"], ["incident", "AI incidents"], ["report", "Citizen reports"], ["camera", "Cameras"]];
export function CitizenMapPage() {
  const [snapshot, setSnapshot] = useState<{ data: MapSnapshot; started: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const [enabled, setEnabled] = useState<MapKind[]>(["road", "incident", "report", "camera"]);
  const [selected, setSelected] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    async function refresh() {
      if (inFlight) return;
      inFlight = true;
      const started = performance.now();
      try {
        const response = await apiFetch("/api/map", { signal: controller.signal });
        if (!response.ok) throw new Error(`Map data unavailable (HTTP ${response.status})`);
        const data: MapSnapshot = await response.json();
        if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) throw new Error("Invalid map data");
        if (!controller.signal.aborted) { setSnapshot({ data, started }); setError(null); }
      } catch (reason) {
        if (!controller.signal.aborted) { setSnapshot(null); setError(reason instanceof Error ? reason.message : "Map data unavailable"); }
      } finally { inFlight = false; if (!controller.signal.aborted) setLoading(false); }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    const clock = window.setInterval(() => setTick(value => value + 1), 1000);
    return () => { controller.abort(); window.clearInterval(timer); window.clearInterval(clock); };
  }, [retry]);
  const features = useMemo(() => snapshot ? expireFeatures(snapshot.data, (performance.now() - snapshot.started) / 1000)
    .filter(feature => enabled.includes(feature.properties.kind)) : [], [snapshot, enabled, tick]);
  const detail = features.find(feature => feature.id === selected);
  return <main className="operations-page cityeye-map-page">
    <PageTitle label="GEOGRAPHIC TRAFFIC VIEW" title="Citizen Map" copy="CityEye observations on Google Maps. Road coverage and incident certainty stay explicit." />
    <div className="map-toolbar" aria-label="Map layers">
      {LAYERS.filter(([kind]) => kind !== "camera" || snapshot?.data.scope !== "PUBLIC").map(([kind, label]) =>
        <label key={kind}><input type="checkbox" checked={enabled.includes(kind)} onChange={() => setEnabled(previous => previous.includes(kind) ? previous.filter(item => item !== kind) : [...previous, kind])} />{label}</label>)}
    </div>
    {error && <div className="command-error" role="alert">{error}<button onClick={() => setRetry(value => value + 1)}>Retry data</button></div>}
    {loading && <p role="status">Loading map observations…</p>}
    <section className="cityeye-map-layout">
      <JourneyMap features={features} onSelect={setSelected} />
      <aside className="map-observations" aria-label="Map observations">
        <h2>{features.length} visible observations</h2>
        {snapshot && snapshot.data.configured_cameras === 0 && <p>No confirmed camera locations are configured. No road or camera position is guessed.</p>}
        {!loading && !error && features.length === 0 && <p>No mapped observations in the enabled layers.</p>}
        {features.map(feature => <button key={feature.id} className={selected === feature.id ? "selected" : ""} onClick={() => setSelected(feature.id)}>
          <i style={{ background: featureColor(feature) }} /><span><strong>{feature.properties.label}</strong><small>{feature.properties.kind.toUpperCase()} · {feature.properties.status}</small></span>
        </button>)}
      </aside>
    </section>
    <section className="map-legend" aria-label="Map legend">
      <span><i style={{ background: "#25a56a" }} />Normal</span><span><i style={{ background: "#e9ae35" }} />Moderate</span>
      <span><i style={{ background: "#ef5350" }} />Heavy congestion</span><span><i style={{ background: "#8796a5" }} />Unknown / stale</span>
      <span><i style={{ background: "#f39c36" }} />Proposed incident</span><span><i style={{ background: "#d34fff" }} />Verified incident</span>
      <span><i style={{ background: "#4f95ff" }} />Citizen report (not AI verification)</span>
    </section>
    {detail && <section className="map-detail" aria-label="Selected map observation">
      <button className="ghost" onClick={() => setSelected(null)}>Close details</button><h2>{detail.properties.label}</h2>
      <p>{detail.properties.status} · {detail.properties.location_accuracy.replace(/_/g, " ")}</p>
      <p>{detail.properties.observed_at ? new Date(detail.properties.observed_at * 1000).toLocaleString() : "Observation time unavailable"}</p>
      {detail.properties.vehicles != null && <p>{detail.properties.vehicles} vehicles observed in the current sample; not throughput.</p>}
      <p>{detail.properties.description}</p>
    </section>}
    <p className="map-notice">{snapshot?.data.notice ?? "Only confirmed coverage can be mapped. Unavailable traffic remains unknown."}</p>
    <p className="map-notice">Stopped vehicle, wrong way, congestion and road blockage use their existing event types. Collision detection and automatic report corroboration are not implemented. Map points do not establish an exact vehicle GPS location.</p>
  </main>;
}
