import { useCallback, useEffect, useState } from "react";
import { fetchEvents, reviewEvent } from "../api/events";
import type { TrafficEvent } from "../types";

const POLL_INTERVAL_MS = 2_000;

export function useEvents() {
  const [events, setEvents] = useState<TrafficEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewingEventId, setReviewingEventId] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await fetchEvents(signal);
      setEvents(result.events);
      setError(null);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError(requestError instanceof Error ? requestError.message : "Unable to load events");
    } finally {
      setLoading(false);
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

  const decide = useCallback(async (eventId: string, decision: "verify" | "dismiss") => {
    setReviewingEventId(eventId);
    try {
      const updated = await reviewEvent(eventId, decision);
      setEvents((current) => current.map((event) => (
        event.event_id === updated.event_id ? updated : event
      )));
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Review action failed");
    } finally {
      setReviewingEventId(null);
    }
  }, []);

  return { events, loading, error, reviewingEventId, refresh, decide };
}
