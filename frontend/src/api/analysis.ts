import type { AnalysisSummary, AnalysisTimeline, ScenarioId, ScenarioInfo } from "../types";

export async function fetchAnalysisSummary(scenarioId: ScenarioId, signal?: AbortSignal): Promise<AnalysisSummary> {
  const response = await fetch(`/api/scenarios/${scenarioId}/analysis/summary`, { signal });
  if (!response.ok) throw new Error(`Analysis request failed with HTTP ${response.status}`);
  return response.json() as Promise<AnalysisSummary>;
}

export async function fetchAnalysisTimeline(scenarioId: ScenarioId, signal?: AbortSignal): Promise<AnalysisTimeline> {
  const response = await fetch(`/api/scenarios/${scenarioId}/analysis/timeline`, { signal });
  if (!response.ok) throw new Error(`Analysis timeline request failed with HTTP ${response.status}`);
  return response.json() as Promise<AnalysisTimeline>;
}

export async function fetchScenarios(signal?: AbortSignal): Promise<ScenarioInfo[]> {
  const response = await fetch("/api/scenarios", { signal });
  if (!response.ok) throw new Error(`Scenario request failed with HTTP ${response.status}`);
  const payload = await response.json() as { scenarios: ScenarioInfo[] };
  return payload.scenarios;
}
