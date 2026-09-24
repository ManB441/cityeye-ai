import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAnalysisSummary, fetchAnalysisTimeline } from "../api/analysis";
import type { AnalysisSummary, AnalysisTimeline, ScenarioId } from "../types";

export function useAnalysis(scenarioId: ScenarioId) {
  const [owner, setOwner] = useState<ScenarioId | null>(null);
  const requestVersion = useRef(0);
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);
  const [timeline, setTimeline] = useState<AnalysisTimeline | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const version = ++requestVersion.current;
    try {
      const [nextSummary, nextTimeline] = await Promise.all([
        fetchAnalysisSummary(scenarioId, signal), fetchAnalysisTimeline(scenarioId, signal),
      ]);
      if (signal?.aborted || version !== requestVersion.current) return;
      setOwner(scenarioId);
      setSummary(nextSummary);
      setTimeline(nextTimeline);
      setError(null);
    } catch (requestError) {
      if (signal?.aborted || version !== requestVersion.current) return;
      setOwner(scenarioId); setSummary(null); setTimeline(null);
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis");
    }
  }, [scenarioId]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  return { summary: owner === scenarioId ? summary : null, timeline: owner === scenarioId ? timeline : null, error: owner === scenarioId ? error : null, refresh };
}
