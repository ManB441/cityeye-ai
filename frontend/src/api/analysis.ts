import type { AnalysisSummary } from "../types";

export async function fetchAnalysisSummary(signal?: AbortSignal): Promise<AnalysisSummary> {
  const response = await fetch("/api/analysis/summary", { signal });
  if (!response.ok) throw new Error(`Analysis request failed with HTTP ${response.status}`);
  return response.json() as Promise<AnalysisSummary>;
}
