import { useCallback, useEffect, useState } from "react";
import { fetchAnalysisSummary, fetchAnalysisTimeline } from "../api/analysis";
import type { AnalysisSummary, AnalysisTimeline, ScenarioId } from "../types";

const POLL_INTERVAL_MS = 2_000;

export function useAnalysis(scenarioId: ScenarioId) {
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);
  const [timeline, setTimeline] = useState<AnalysisTimeline | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextSummary, nextTimeline] = await Promise.all([
        fetchAnalysisSummary(scenarioId, signal), fetchAnalysisTimeline(scenarioId, signal),
      ]);
      setSummary(nextSummary);
      setTimeline(nextTimeline);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis");
    }
  }, [scenarioId]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  return { summary, timeline, error, refresh };
}
