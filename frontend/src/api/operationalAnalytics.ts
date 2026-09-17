import type { OperationalAnalytics } from "../types";

export async function fetchOperationalAnalytics(
  cameraId: string,
  start: number,
  end: number,
  signal?: AbortSignal,
): Promise<OperationalAnalytics> {
  const query = new URLSearchParams({ camera_id: cameraId, start: String(start), end: String(end) });
  const response = await fetch(`/api/analytics/traffic?${query}`, { signal });
  if (!response.ok) throw new Error(`Analytics request failed with HTTP ${response.status}`);
  return response.json() as Promise<OperationalAnalytics>;
}
