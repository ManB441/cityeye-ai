import { useCallback, useEffect, useState } from "react";
import { fetchAnalysisSummary } from "../api/analysis";
import type { AnalysisSummary } from "../types";

const POLL_INTERVAL_MS = 2_000;

export function useAnalysis() {
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      setSummary(await fetchAnalysisSummary(signal));
      setError(null);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError(requestError instanceof Error ? requestError.message : "Unable to load analysis");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  return { summary, error, refresh };
}
