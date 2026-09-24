import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchEvents, reviewEvent } from "../api/events";
import type { ScenarioId, TrafficEvent } from "../types";

const POLL_INTERVAL_MS = 2_000;

export function useEvents(scenarioId: ScenarioId, selection: unknown = scenarioId) {
  // Identity distinguishes A → B → A from the original visit to A.
  const scope = useMemo(() => ({}), [scenarioId, selection]);
  const selected = useRef(scope);
  selected.current = scope;
  const [owner, setOwner] = useState<object | null>(null);
  const requestVersion = useRef(0);
  const pending = useRef<{ scope: object; eventId: string } | null>(null);
  const [events, setEvents] = useState<TrafficEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<typeof pending.current>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const version = ++requestVersion.current;
    const current = () => !signal?.aborted && selected.current === scope && version === requestVersion.current;
    try {
      const result = await fetchEvents(scenarioId, signal);
      if (!current()) return;
      setOwner(scope);
      setEvents(result.events);
      setError(null);
    } catch (requestError) {
      if (!current()) return;
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setOwner(scope);
      setError(requestError instanceof Error ? requestError.message : "Unable to load events");
    } finally {
      if (current()) setLoading(false);
    }
  }, [scenarioId, scope]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(controller.signal), POLL_INTERVAL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [refresh]);

  const decide = useCallback(async (eventId: string, decision: "verify" | "dismiss") => {
    if (pending.current?.scope === scope) return;
    const operation = { scope, eventId };
    pending.current = operation;
    setReviewing(operation);
    ++requestVersion.current;
    try {
      const updated = await reviewEvent(eventId, decision, scenarioId);
      if (selected.current !== scope) return;
      ++requestVersion.current;
      setEvents(current => current.map(event => event.event_id === updated.event_id ? updated : event));
      setError(null);
      return updated;
    } finally {
      if (pending.current === operation) {
        pending.current = null;
        setReviewing(null);
      }
    }
  }, [scenarioId, scope]);

  return {
    events: owner === scope ? events : [], loading: owner !== scope || loading,
    error: owner === scope ? error : null,
    reviewingEventId: reviewing?.scope === scope ? reviewing.eventId : null, refresh, decide,
  };
}
