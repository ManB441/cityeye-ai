import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { fetchEvents, reviewEvent } from "../api/events";
import { useEvents } from "./useEvents";
import type { ScenarioId, TrafficEvent } from "../types";
vi.mock("../api/events", () => ({ fetchEvents: vi.fn(), reviewEvent: vi.fn() }));
const proposal = { event_id: "same-id", status: "PROPOSED" } as TrafficEvent;
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("ignores the original review after A → B → A and does not clear the new pending review", async () => {
  vi.mocked(fetchEvents).mockResolvedValue({ events: [proposal], total: 1 });
  const old = deferred<TrafficEvent>(); const current = deferred<TrafficEvent>();
  vi.mocked(reviewEvent).mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
  const hook = renderHook(({ id }: { id: ScenarioId }) => useEvents(id), { initialProps: { id: "normal_traffic" as ScenarioId } });
  await waitFor(() => expect(hook.result.current.events).toHaveLength(1));
  let first!: Promise<unknown>;
  act(() => { first = hook.result.current.decide("same-id", "verify"); });
  hook.rerender({ id: "congestion" }); hook.rerender({ id: "normal_traffic" });
  await waitFor(() => expect(hook.result.current.events).toHaveLength(1));
  expect(hook.result.current.reviewingEventId).toBeNull();
  let second!: Promise<unknown>;
  act(() => { second = hook.result.current.decide("same-id", "dismiss"); });
  await act(async () => { old.resolve({ ...proposal, status: "VERIFIED" }); await first; });
  expect(hook.result.current.events[0].status).toBe("PROPOSED");
  expect(hook.result.current.reviewingEventId).toBe("same-id");
  await act(async () => { current.resolve({ ...proposal, status: "DISMISSED" }); await second; });
  expect(hook.result.current.events[0].status).toBe("DISMISSED");
  expect(hook.result.current.reviewingEventId).toBeNull();
});

it("rejects a GET begun during a recorded review when it resolves after the save", async () => {
  vi.mocked(fetchEvents).mockResolvedValue({ events: [proposal], total: 1 });
  const save = deferred<TrafficEvent>();
  vi.mocked(reviewEvent).mockReturnValue(save.promise);
  const hook = renderHook(() => useEvents("normal_traffic"));
  await waitFor(() => expect(hook.result.current.events).toHaveLength(1));
  let review!: Promise<unknown>; let refresh!: Promise<unknown>;
  act(() => { review = hook.result.current.decide("same-id", "verify"); });
  const get = deferred<{ events: TrafficEvent[]; total: number }>();
  vi.mocked(fetchEvents).mockReturnValueOnce(get.promise);
  act(() => { refresh = hook.result.current.refresh(); });
  await act(async () => { save.resolve({ ...proposal, status: "VERIFIED" }); await review; });
  await act(async () => { get.resolve({ events: [proposal], total: 1 }); await refresh; });
  expect(hook.result.current.events[0].status).toBe("VERIFIED");
});
