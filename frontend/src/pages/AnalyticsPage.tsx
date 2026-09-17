import { useEffect, useMemo, useState } from "react";
import { fetchLiveCameras } from "../api/live";
import { fetchOperationalAnalytics } from "../api/operationalAnalytics";
import type { CameraHealth, OperationalAnalytics } from "../types";
import { PageTitle } from "./CamerasPage";

type RangePreset = "today" | "24h" | "7d" | "30d";
const CAMERA_NAMES: Record<string, string> = { "camera-3": "DVR Camera 3", "camera-5": "DVR Camera 5", "camera-7": "DVR Camera 7" };
const RANGE_LABELS: Record<RangePreset, string> = { today: "Today", "24h": "24H", "7d": "7D", "30d": "30D" };

function rangeStart(preset: RangePreset, end: number): number {
  if (preset === "today") {
    const date = new Date(end * 1000);
    date.setHours(0, 0, 0, 0);
    return date.getTime() / 1000;
  }
  const hours = preset === "24h" ? 24 : preset === "7d" ? 168 : 720;
  return end - hours * 3600;
}

function formatDate(timestamp: number | null, includeDate = true): string {
  if (timestamp === null) return "—";
  return new Intl.DateTimeFormat(undefined, { ...(includeDate ? { month: "short", day: "numeric" } : {}), hour: "numeric", minute: "2-digit" }).format(timestamp * 1000);
}

function TrafficChart({ analytics }: { analytics: OperationalAnalytics }) {
  const series = analytics.traffic_series;
  if (!series.length) return <div className="analytics-empty compact">No traffic samples in this period.</div>;
  const maxValue = Math.max(1, ...series.map((point) => point.average_vehicles_observed));
  const coordinates = series.map((point, index) => ({
    point,
    x: series.length === 1 ? 50 : (index / (series.length - 1)) * 100,
    y: 90 - (point.average_vehicles_observed / maxValue) * 75,
  }));
  return <div className="traffic-chart" aria-label="Traffic activity over time">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Average vehicles observed by time bucket">
      <line x1="0" y1="90" x2="100" y2="90" /><line x1="0" y1="52" x2="100" y2="52" /><line x1="0" y1="15" x2="100" y2="15" />
      <polyline points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")} />
      {coordinates.map(({ point, x, y }) => <circle key={point.timestamp} cx={x} cy={y} r="1.7"><title>{formatDate(point.timestamp)} · {point.average_vehicles_observed} average vehicles</title></circle>)}
    </svg>
    <div><span>{formatDate(series[0].timestamp)}</span><span>{formatDate(series[series.length - 1]?.timestamp ?? null)}</span></div>
  </div>;
}

export function AnalyticsPage() {
  const [cameras, setCameras] = useState<CameraHealth[]>([]);
  const [cameraId, setCameraId] = useState("camera-3");
  const [preset, setPreset] = useState<RangePreset>("today");
  const [analytics, setAnalytics] = useState<OperationalAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void fetchLiveCameras(controller.signal).then((items) => {
      setCameras(items);
      if (items.length && !items.some((item) => item.camera_id === cameraId)) setCameraId(items[0].camera_id);
    }).catch(() => setCameras([]));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const end = Date.now() / 1000;
    setLoading(true); setError(null);
    void fetchOperationalAnalytics(cameraId, rangeStart(preset, end), end, controller.signal)
      .then((result) => { if (active) setAnalytics(result); })
      .catch((requestError) => {
        if (active && !(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setAnalytics(null);
          setError(requestError instanceof Error ? requestError.message : "Analytics are unavailable");
        }
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [cameraId, preset, requestVersion]);

  const composition = useMemo(() => Object.entries(analytics?.vehicle_composition_observations ?? {}).filter(([, value]) => value > 0), [analytics]);
  const compositionTotal = composition.reduce((sum, [, value]) => sum + value, 0);
  const hasData = Boolean(analytics?.samples);

  return <main className="operations-page analytics-page">
    <PageTitle label="TRAFFIC INTELLIGENCE" title="Operational Analytics" copy="Real historical observations collected from active CityEye cameras." />
    <section className="analytics-controls" aria-label="Analytics filters">
      <label>Camera<select value={cameraId} onChange={(event) => setCameraId(event.target.value)}>{(cameras.length ? cameras : [{ camera_id: "camera-3" } as CameraHealth]).map((camera) => <option key={camera.camera_id} value={camera.camera_id}>{CAMERA_NAMES[camera.camera_id] ?? camera.camera_id}</option>)}</select></label>
      <div><span>Range</span>{(Object.keys(RANGE_LABELS) as RangePreset[]).map((range) => <button key={range} className={preset === range ? "active" : ""} onClick={() => setPreset(range)}>{RANGE_LABELS[range]}</button>)}</div>
    </section>
    {error && <div className="command-error" role="alert"><span>{error}</span><button onClick={() => setRequestVersion((value) => value + 1)}>Retry</button></div>}
    {loading && <div className="analytics-empty">Loading real traffic history…</div>}
    {!loading && !error && analytics && !hasData && <div className="analytics-empty"><strong>Traffic history is being collected.</strong><span>Analytics will appear as {CAMERA_NAMES[cameraId] ?? cameraId} observations are stored.</span>{analytics.data_since && <small>Historical data is available from {formatDate(analytics.data_since)}.</small>}</div>}
    {!loading && !error && analytics && hasData && <>
      <p className="analytics-availability">Traffic data collected since <strong>{formatDate(analytics.data_since)}</strong>. Showing {analytics.samples} real one-minute sample{analytics.samples === 1 ? "" : "s"} available in this selection.</p>
      <section className="analytics-summary">
        <article><span>Average Vehicles Observed</span><strong>{analytics.average_vehicles_observed?.toFixed(1)}</strong><small>Active detections per stored sample</small></article>
        <article><span>Peak Traffic Period</span><strong>{formatDate(analytics.peak_period_start, false)}</strong><small>{analytics.peak_vehicle_count?.toFixed(1)} average vehicles in bucket</small></article>
        <article><span>Congestion Duration</span><strong>{analytics.congestion_duration_minutes.toFixed(0)} min</strong><small>{analytics.congestion_episodes} recorded episode{analytics.congestion_episodes === 1 ? "" : "s"}</small></article>
        <article><span>Incidents</span><strong>{analytics.incident_count}</strong><small>Persisted events in period</small></article>
      </section>
      <section className="analytics-grid real-analytics-grid">
        <article className="analytics-panel wide"><div className="analytics-panel-heading"><div><span>TRAFFIC HISTORY</span><h2>Traffic Activity Over Time</h2></div><small>{Math.round(analytics.bucket_seconds / 60)}-minute buckets</small></div><TrafficChart analytics={analytics} /></article>
        <article className="analytics-panel"><span>VEHICLE COMPOSITION</span><h2>Observed detection share</h2>{composition.length ? <div className="composition-list">{composition.map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${(value / compositionTotal) * 100}%` }} /></i><strong>{value}</strong></div>)}</div> : <p>No vehicle detections recorded during this period.</p>}<small>Counts are sampled observations, not unique vehicles passed.</small></article>
        <article className="analytics-panel"><span>CONGESTION HISTORY</span><h2>{analytics.congestion_episodes ? `${analytics.congestion_episodes} congestion episode${analytics.congestion_episodes === 1 ? "" : "s"}` : "No congestion recorded"}</h2><p>{analytics.congestion_episodes ? `Approximately ${analytics.congestion_duration_minutes.toFixed(0)} minutes were classified as congested.` : "No congestion recorded during this period."}</p></article>
        <article className="analytics-panel"><span>INCIDENT ANALYTICS</span><h2>Persisted municipal events</h2>{Object.keys(analytics.incidents_by_type).length ? <><div className="analytics-key-values">{Object.entries(analytics.incidents_by_type).map(([type, count]) => <div key={type}><span>{type.split("_").join(" ")}</span><strong>{count}</strong></div>)}</div><small>Review status</small><div className="analytics-key-values">{Object.entries(analytics.incidents_by_status).map(([status, count]) => <div key={status}><span>{status}</span><strong>{count}</strong></div>)}</div></> : <p>No incidents recorded during this period.</p>}</article>
        <article className="analytics-panel"><span>DATA QUALITY</span><h2>{analytics.observed_minutes.toFixed(0)} minutes observed</h2><div className="analytics-key-values"><div><span>Stored samples</span><strong>{analytics.samples}</strong></div><div><span>First sample</span><strong>{formatDate(analytics.first_sample_at)}</strong></div><div><span>Latest sample</span><strong>{formatDate(analytics.latest_sample_at)}</strong></div><div><span>Average capture / AI</span><strong>{analytics.average_capture_fps?.toFixed(1)} / {analytics.average_ai_fps?.toFixed(1)} FPS</strong></div></div></article>
        <article className="analytics-panel future-secondary"><span>PREDICTION</span><h2>Prediction unavailable</h2><p>Historical baseline required. Currently collected: {analytics.observed_minutes.toFixed(0)} minutes.</p></article>
        <article className="analytics-panel future-secondary"><span>MULTI-CAMERA ANALYTICS</span><h2>Requires calibrated sequential cameras</h2><p>Camera 5 and Camera 7 are disabled in this environment. No multi-camera values are calculated.</p></article>
      </section>
    </>}
  </main>;
}
