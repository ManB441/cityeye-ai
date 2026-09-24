import { apiFetch } from "./auth";
import type { EventListResponse, ScenarioId, TrafficEvent } from "../types";
import { authorizationHeaders } from "./auth";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Backend request failed with HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export async function fetchEvents(scenarioId: ScenarioId, signal?: AbortSignal): Promise<EventListResponse> {
  const payload = await parseResponse<EventListResponse>(
    await apiFetch(`/api/scenarios/${scenarioId}/events`, { signal }),
  );
  if (!Array.isArray(payload.events) || payload.total !== payload.events.length) {
    throw new Error("Backend returned an invalid Event list");
  }
  return payload;
}

export async function reviewEvent(
  eventId: string,
  decision: "verify" | "dismiss",
  scenarioId: ScenarioId,
): Promise<TrafficEvent> {
  const headers = authorizationHeaders();
  return parseResponse<TrafficEvent>(await apiFetch(
    `/api/scenarios/${scenarioId}/events/${encodeURIComponent(eventId)}/${decision}`,
    {
      method: "POST",
      ...(headers ? { headers } : {}),
    },
  ));
}

export function evidenceUrl(evidenceImage: string, scenarioId?: ScenarioId): string {
  const filename = evidenceImage.split("/").pop();
  return filename ? (scenarioId ? `/evidence/scenarios/${scenarioId}/${encodeURIComponent(filename)}` : `/evidence/${encodeURIComponent(filename)}`) : "";
}

export async function fetchPersistentEvents(signal?: AbortSignal): Promise<EventListResponse> {
  return parseResponse<EventListResponse>(await apiFetch("/api/events", { signal }));
}

export async function reviewPersistentEvent(eventId: string, decision: "verify" | "dismiss"): Promise<TrafficEvent> {
  return parseResponse<TrafficEvent>(await apiFetch(`/api/events/${encodeURIComponent(eventId)}/${decision}`, { method: "POST" }));
}

export function liveIncidentEvidenceUrl(event: TrafficEvent): string {
  const filename = event.evidence_image.split("/").pop();
  return event.source_id && filename
    ? `/evidence/live-cameras/${encodeURIComponent(event.source_id)}/${encodeURIComponent(filename)}` : "";
}
