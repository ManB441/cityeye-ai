import type { CameraHealth, EventListResponse, LiveMetrics, TrafficEvent } from "../types";
import { authorizationHeaders } from "./auth";

async function read<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Backend request failed with HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export function fetchLiveCameras(signal?: AbortSignal): Promise<CameraHealth[]> {
  return read("/api/live-cameras", { signal });
}

export function fetchLiveStatus(cameraId: string, signal?: AbortSignal): Promise<CameraHealth> {
  return read(`/api/live-cameras/${encodeURIComponent(cameraId)}/status`, { signal });
}

export function fetchLiveMetrics(cameraId: string, signal?: AbortSignal): Promise<LiveMetrics> {
  return read(`/api/live-cameras/${encodeURIComponent(cameraId)}/metrics`, { signal });
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
