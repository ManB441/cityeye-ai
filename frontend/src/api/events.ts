import type { EventListResponse, TrafficEvent } from "../types";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Backend request failed with HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export async function fetchEvents(signal?: AbortSignal): Promise<EventListResponse> {
  const payload = await parseResponse<EventListResponse>(
    await fetch("/api/events", { signal }),
  );
  if (!Array.isArray(payload.events) || payload.total !== payload.events.length) {
    throw new Error("Backend returned an invalid Event list");
  }
  return payload;
}

export async function reviewEvent(
  eventId: string,
  decision: "verify" | "dismiss",
): Promise<TrafficEvent> {
  return parseResponse<TrafficEvent>(await fetch(
    `/api/events/${encodeURIComponent(eventId)}/${decision}`,
    { method: "POST" },
  ));
}

export function evidenceUrl(evidenceImage: string): string {
  const filename = evidenceImage.split("/").pop();
  return filename ? `/evidence/${encodeURIComponent(filename)}` : "";
}
