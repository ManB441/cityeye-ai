import { apiFetch } from "./auth";
import type { AnalysisSummary, AnalysisTimeline, ScenarioId, ScenarioInfo, ScenarioSnapshot } from "../types";

export async function fetchAnalysisSummary(scenarioId: ScenarioId, signal?: AbortSignal): Promise<AnalysisSummary> {
  const response = await apiFetch(`/api/scenarios/${scenarioId}/analysis/summary`, { signal });
  if (!response.ok) throw new Error(`Analysis request failed with HTTP ${response.status}`);
  return response.json() as Promise<AnalysisSummary>;
}

export async function fetchAnalysisTimeline(scenarioId: ScenarioId, signal?: AbortSignal): Promise<AnalysisTimeline> {
  const response = await apiFetch(`/api/scenarios/${scenarioId}/analysis/timeline`, { signal });
  if (!response.ok) throw new Error(`Analysis timeline request failed with HTTP ${response.status}`);
  return response.json() as Promise<AnalysisTimeline>;
}

export async function fetchScenarios(signal?: AbortSignal): Promise<ScenarioInfo[]> {
  const response = await apiFetch("/api/scenarios", { signal });
  if (!response.ok) throw new Error(`Scenario request failed with HTTP ${response.status}`);
  const payload = await response.json() as { scenarios: ScenarioInfo[] };
  return payload.scenarios;
}

export async function fetchScenarioSnapshots(signal?: AbortSignal): Promise<ScenarioSnapshot[]> {
  const scenarios = await fetchScenarios(signal);
  return Promise.all(scenarios.map(async (scenario) => {
    const [summaryResult, eventsResult] = await Promise.allSettled([
      fetchAnalysisSummary(scenario.scenario_id, signal),
      apiFetch(`/api/scenarios/${scenario.scenario_id}/events`, { signal }).then(async (response) => {
        if (!response.ok) throw new Error(`Event request failed with HTTP ${response.status}`);
        return response.json() as Promise<{ events: ScenarioSnapshot["events"] }>;
      }),
    ]);
    return {
      scenario,
      summary: summaryResult.status === "fulfilled" ? summaryResult.value : null,
      events: eventsResult.status === "fulfilled" ? eventsResult.value.events : [],
      summaryError: summaryResult.status === "rejected",
      eventsError: eventsResult.status === "rejected",
    };
  }));
}
