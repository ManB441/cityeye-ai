import { apiFetch } from "./auth";
import type { CameraHealth, EventListResponse, LiveMetricsSnapshot, TrafficEvent } from "../types";
import { authorizationHeaders } from "./auth";

async function read<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await apiFetch(url, options);
  if (!response.ok) throw new Error(`Backend request failed with HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function deadline(seconds: number, started: number): number {
  // Subtract the whole round trip conservatively; never trust the browser wall clock.
  return started + Math.max(0, Number.isFinite(seconds) ? seconds : 0) * 1000;
}

export async function fetchLiveCameras(signal?: AbortSignal): Promise<CameraHealth[]> {
  const started = performance.now();
  const cameras = await read<CameraHealth[]>("/api/live-cameras", { signal });
  return cameras.map((camera) => ({ ...camera, expires_at: deadline(camera.valid_for_seconds, started) }));
}

export async function fetchLiveStatus(cameraId: string, signal?: AbortSignal): Promise<CameraHealth> {
  const started = performance.now();
  const health = await read<CameraHealth>(`/api/live-cameras/${encodeURIComponent(cameraId)}/status`, { signal });
  return { ...health, expires_at: deadline(health.valid_for_seconds, started) };
}

export async function fetchLiveMetrics(cameraId: string, signal?: AbortSignal): Promise<LiveMetricsSnapshot> {
  const started = performance.now();
  const snapshot = await read<LiveMetricsSnapshot>(`/api/live-cameras/${encodeURIComponent(cameraId)}/metrics`, { signal });
  return { ...snapshot, expires_at: deadline(snapshot.valid_for_seconds, started),
    health: { ...snapshot.health, expires_at: deadline(snapshot.health.valid_for_seconds, started) } };
}

export function fetchLiveEvents(cameraId: string, signal?: AbortSignal): Promise<EventListResponse> {
  return read(`/api/live-cameras/${encodeURIComponent(cameraId)}/events`, { signal });
}

export function reviewLiveEvent(cameraId: string, eventId: string, decision: "verify" | "dismiss"): Promise<TrafficEvent> {
  const headers = authorizationHeaders();
  return read(`/api/live-cameras/${encodeURIComponent(cameraId)}/events/${encodeURIComponent(eventId)}/${decision}`, {
    method: "POST",
    ...(headers ? { headers } : {}),
  });
}

export function liveEvidenceUrl(cameraId: string, evidenceImage: string): string {
  const filename = evidenceImage.split("/").pop();
  return filename ? `/evidence/live-cameras/${encodeURIComponent(cameraId)}/${encodeURIComponent(filename)}` : "";
}
