import { useEffect, useState } from "react";
import type { CameraHealth, LiveMetrics, LiveMetricsSnapshot } from "../types";

export function useFreshnessClock() {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    const tick = () => setNow(performance.now());
    const timer = window.setInterval(tick, 250);
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", tick);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", tick); document.removeEventListener("visibilitychange", tick); };
  }, []);
  return now;
}

export function cameraIsOnline(health: CameraHealth | null | undefined, now: number): boolean {
  return health?.state === "ONLINE" && Number.isFinite(health.expires_at) && health.expires_at! > now;
}

export function cameraStateLabel(health: CameraHealth | null | undefined, now: number): string {
  return health?.state === "ONLINE" && !cameraIsOnline(health, now) ? "UNAVAILABLE" : health?.state ?? "CONNECTING";
}

export function currentLiveMetrics(snapshot: LiveMetricsSnapshot | null, health: CameraHealth | null | undefined, cameraId: string | null, now: number): LiveMetrics | null {
  if (!cameraId || !snapshot || snapshot.camera_id !== cameraId || snapshot.health.camera_id !== cameraId
    || health?.camera_id !== cameraId || !cameraIsOnline(health, now)
    || !cameraIsOnline(snapshot.health, now) || snapshot.reason !== "FRESH"
    || !Number.isFinite(snapshot.expires_at) || snapshot.expires_at <= now
    || !snapshot.metrics || snapshot.metrics.generation !== snapshot.health.generation
    || snapshot.metrics.generation !== health.generation
    || snapshot.health.last_connected_at !== health.last_connected_at) return null;
  return snapshot.metrics;
}

export function trafficCondition(state: string | undefined): string {
  switch (state) {
    case "NORMAL": return "Normal";
    case "MODERATE": return "Moderate";
    case "HEAVY_CONGESTION": return "Heavy congestion";
    case "CONGESTED": return "Congested";
    default: return "Unknown";
  }
}
