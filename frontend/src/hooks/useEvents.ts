import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEvents, reviewEvent } from "../api/events";
import type { ScenarioId, TrafficEvent } from "../types";

const POLL_INTERVAL_MS = 2_000;

export function useEvents(scenarioId: ScenarioId) {
  const selectedSource = useRef(scenarioId);
  selectedSource.current = scenarioId;
  const [owner, setOwner] = useState<ScenarioId | null>(null);
  const requestVersion = useRef(0);
  const [events, setEvents] = useState<TrafficEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewingEventId, setReviewingEventId] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const version = ++requestVersion.current;
    try {
      const result = await fetchEvents(scenarioId, signal);
      if (signal?.aborted || version !== requestVersion.current) return;
      setOwner(scenarioId);
      setEvents(result.events);
      setError(null);
    } catch (requestError) {
      if (signal?.aborted || version !== requestVersion.current) return;
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError(requestError instanceof Error ? requestError.message : "Unable to load events");
    } finally {
      setLoading(false);
    }
  }, [scenarioId]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(controller.signal), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  const decide = useCallback(async (eventId: string, decision: "verify" | "dismiss") => {
    setReviewingEventId(eventId);
    try {
      const updated = await reviewEvent(eventId, decision, scenarioId);
      if (selectedSource.current !== scenarioId) return;
      setEvents((current) => current.map((event) => (
        event.event_id === updated.event_id ? updated : event
      )));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Review action failed");
    } finally {
      setReviewingEventId(null);
    }
  }, [scenarioId]);

  return { events: owner === scenarioId ? events : [], loading: owner !== scenarioId || loading, error: owner === scenarioId ? error : null, reviewingEventId, refresh, decide };
}
