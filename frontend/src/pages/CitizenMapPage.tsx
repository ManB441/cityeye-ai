import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api/auth";
import { JourneyMap } from "../maps/JourneyMap";
import { expireFeatures, featureColor, type MapKind, type MapSnapshot } from "../maps/model";

const LAYERS: [MapKind, string][] = [["road", "Road conditions"], ["incident", "AI incidents"], ["report", "Citizen reports"], ["camera", "Cameras"]];
export function CitizenMapPage() {
  const [snapshot, setSnapshot] = useState<{ data: MapSnapshot; started: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const [enabled, setEnabled] = useState<MapKind[]>(["road", "incident", "report", "camera"]);
  const [selected, setSelected] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [layersOpen, setLayersOpen] = useState(false);
  const [observationsOpen, setObservationsOpen] = useState(false);
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
  return <main className="cityeye-map-page">
    <section className="map-app-shell" aria-label="Citizen Map">
      <JourneyMap features={features} onSelect={setSelected} />
      <div className="map-identity"><strong>CityEye</strong><span>خريطة المدينة</span></div>
      {error && <div className="map-data-error" role="alert">تعذر تحديث بيانات CityEye.<button onClick={() => setRetry(value => value + 1)}>حاول مرة أخرى</button></div>}
      {loading && <p className="map-loading" role="status">جارٍ تحميل ملاحظات الخريطة…</p>}
      <section className="map-layer-control" aria-label="Map layers">
        <button type="button" aria-expanded={layersOpen} onClick={() => setLayersOpen(value => !value)}>الطبقات</button>
        {layersOpen && <div className="map-toolbar">
          {LAYERS.filter(([kind]) => kind !== "camera" || snapshot?.data.scope !== "PUBLIC").map(([kind, label]) =>
            <label key={kind}><input type="checkbox" checked={enabled.includes(kind)} onChange={() => setEnabled(previous => previous.includes(kind) ? previous.filter(item => item !== kind) : [...previous, kind])} />{label}</label>)}
        </div>}
      </section>
      <button className="map-observations-toggle" type="button" onClick={() => setObservationsOpen(value => !value)} aria-expanded={observationsOpen}>{features.length} ملاحظة قريبة</button>
      <aside className={`map-observations ${observationsOpen ? "open" : ""}`} aria-label="Map observations">
        <button className="map-observations-close" type="button" onClick={() => setObservationsOpen(false)}>إغلاق</button>
        <h2>{features.length} visible observations</h2>
        {snapshot && snapshot.data.configured_cameras === 0 && <p>No confirmed camera locations are configured. No road or camera position is guessed.</p>}
        {!loading && !error && features.length === 0 && <p>No mapped observations in the enabled layers.</p>}
        {features.map(feature => <button key={feature.id} className={selected === feature.id ? "selected" : ""} onClick={() => setSelected(feature.id)}>
          <i style={{ background: featureColor(feature) }} /><span><strong>{feature.properties.label}</strong><small>{feature.properties.kind.toUpperCase()} · {feature.properties.status}</small></span>
        </button>)}
      </aside>
      <section className="map-legend" aria-label="Map legend">
        <span><i style={{ background: "#6e956d" }} />Normal</span><span><i style={{ background: "#d6a84f" }} />Moderate</span>
        <span><i style={{ background: "#c96555" }} />Heavy congestion</span><span><i style={{ background: "#8796a5" }} />Unknown</span>
      </section>
      {detail && <section className="map-detail" aria-label="Selected map observation">
        <button className="ghost" onClick={() => setSelected(null)}>×</button><h2>{detail.properties.label}</h2>
        <p>{detail.properties.status} · {detail.properties.location_accuracy.replace(/_/g, " ")}</p>
        <p>{detail.properties.observed_at ? new Date(detail.properties.observed_at * 1000).toLocaleString() : "وقت الملاحظة غير متاح"}</p>
        {detail.properties.vehicles != null && <p>{detail.properties.vehicles} مركبة في العينة الحالية.</p>}
        <p>{detail.properties.description}</p>
      </section>}
      {!loading && !error && features.length === 0 && <p className="map-empty-notice">لا توجد ملاحظات قريبة متموضعة حاليًا.</p>}
    </section>
  </main>;
}
