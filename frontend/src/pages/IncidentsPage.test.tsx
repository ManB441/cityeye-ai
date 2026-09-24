import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthState } from "../hooks/useAuth";
import type { TrafficEvent } from "../types";
import { IncidentsPage } from "./IncidentsPage";

const live: TrafficEvent = {
  event_id: "live-uuid", event_type: "WRONG_WAY", timestamp: 1789670000,
  confidence: 0.91, severity: "HIGH", explanation: "Controlled live proposal",
  camera_name: "DVR Camera 3", latitude: 0, longitude: 0,
  evidence_image: "evidence/live.jpg", status: "PROPOSED",
  source_type: "LIVE_CAMERA", source_id: "camera-3",
  details: { track_id: 7, direction_score: 0.91, timestamp_kind: "WALL_CLOCK_UNIX" },
};
const recorded: TrafficEvent = {
  ...live, event_id: "recorded-uuid", event_type: "CONGESTION", timestamp: 5,
  camera_name: "Demo Camera", explanation: "Recorded congestion", evidence_image: "evidence/demo.jpg",
  source_type: undefined, source_id: undefined, details: null,
};
function auth(role: "CITIZEN" | "EMPLOYEE" | "ADMIN"): AuthState {
  return { user: { user_id: role, username: role, role }, authRequired: true,
    initialized: true, loading: false, error: null, login: vi.fn(), logout: vi.fn() };
}
function backend() {
  let stored = { ...live };
  const mock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
    if (url === "/api/events") return json({ events: [stored, recorded], total: 2 });
    if (url === "/api/scenarios") return json({ scenarios: [{ scenario_id: "congestion", title: "Heavy Congestion" }] });
    if (url.endsWith("/analysis/summary")) return json({ status: "READY" });
    if (url === "/api/scenarios/congestion/events") return json({ events: [recorded], total: 1 });
    if (url.startsWith("/api/events/live-uuid/") && init?.method === "POST") {
      stored = { ...stored, status: url.endsWith("/verify") ? "VERIFIED" : "DISMISSED" };
      return json(stored);
    }
    return new Response("{}", { status: 404 });
  });
  return mock;
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Unified incidents", () => {
  it("shows persistent LIVE and recorded demo incidents once, with live evidence and safe wrong-way metadata", async () => {
    backend(); render(<IncidentsPage auth={auth("EMPLOYEE")} />);
    await screen.findByText("LIVE · DVR Camera 3");
    await screen.findByText("RECORDED DEMO · Demo Camera");
    expect(screen.getAllByText("Recorded congestion")).toHaveLength(1);
    const row = screen.getByText("LIVE · DVR Camera 3").closest("article")!;
    expect(row.querySelector("img")).toHaveAttribute("src", "/evidence/live-cameras/camera-3/live.jpg");
    fireEvent.click(within(row).getByRole("button", { name: "View" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("img")).toHaveAttribute("src", "/evidence/live-cameras/camera-3/live.jpg");
    expect(within(dialog).getByText("Observed at")).toBeInTheDocument();
    expect(within(dialog).queryByText("Stationary duration")).not.toBeInTheDocument();
  });
  it("keeps Operator decisions disabled for both sources", async () => {
    backend(); render(<IncidentsPage auth={auth("CITIZEN")} />);
    await screen.findByText("LIVE · DVR Camera 3");
    await screen.findByText("RECORDED DEMO · Demo Camera");
    for (const button of screen.getAllByRole("button", { name: /^(Verify|Dismiss)$/ })) expect(button).toBeDisabled();
  });
  it.each([
    ["EMPLOYEE", "Verify", "VERIFIED"], ["EMPLOYEE", "Dismiss", "DISMISSED"],
    ["ADMIN", "Verify", "VERIFIED"], ["ADMIN", "Dismiss", "DISMISSED"],
  ] as const)("%s can %s and the persisted decision survives remount", async (role, action, status) => {
    const mock = backend(); const view = render(<IncidentsPage auth={auth(role)} />);
    const label = await screen.findByText("LIVE · DVR Camera 3");
    fireEvent.click(within(label.closest("article")!).getByRole("button", { name: action }));
    await waitFor(() => expect(within(label.closest("article")!).getByText(status)).toBeInTheDocument());
    expect(mock).toHaveBeenCalledWith(`/api/events/live-uuid/${action.toLowerCase()}`, { method: "POST" });
    view.unmount(); render(<IncidentsPage auth={auth(role)} />);
    const restored = await screen.findByText("LIVE · DVR Camera 3");
    expect(within(restored.closest("article")!).getByText(status)).toBeInTheDocument();
  });
});

it("refreshes recorded incidents and their open detail after an external review", async () => {
  const mock = backend(); const original = mock.getMockImplementation()!;
  let status = "PROPOSED";
  mock.mockImplementation(async (input, init) => String(input) === "/api/scenarios/congestion/events"
    ? new Response(JSON.stringify({ events: [{ ...recorded, status }], total: 1 }))
    : original(input, init));
  render(<IncidentsPage auth={auth("EMPLOYEE")} />);
  const label = await screen.findByText("RECORDED DEMO · Demo Camera");
  fireEvent.click(within(label.closest("article")!).getByRole("button", { name: "View" }));
  status = "VERIFIED";
  await waitFor(() => expect(within(screen.getByRole("dialog")).getByText("VERIFIED")).toBeInTheDocument(), { timeout: 3500 });
  expect(within(label.closest("article")!).getByText("VERIFIED")).toBeInTheDocument();
});


it.each(["Verify", "Dismiss"])("ignores a recorded poll started before %s completes", async (action) => {
  const mock = backend(); const original = mock.getMockImplementation()!;
  let hold = false; let release: ((response: Response) => void) | undefined;
  const status = action === "Verify" ? "VERIFIED" : "DISMISSED";
  mock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === `/api/scenarios/congestion/events/recorded-uuid/${action.toLowerCase()}`)
      return new Response(JSON.stringify({ ...recorded, status }));
    if (hold && url === "/api/scenarios/congestion/events") {
      hold = false;
      return new Promise<Response>(resolve => { release = resolve; });
    }
    return original(input, init);
  });
  render(<IncidentsPage auth={auth("EMPLOYEE")} />);
  const label = await screen.findByText("RECORDED DEMO · Demo Camera");
  const row = label.closest("article")!;
  fireEvent.click(within(row).getByRole("button", { name: "View" }));
  hold = true;
  await waitFor(() => expect(release).toBeDefined(), { timeout: 3000 });
  fireEvent.click(within(row).getByRole("button", { name: action }));
  await waitFor(() => expect(within(row).getByText(status)).toBeInTheDocument());
  await act(async () => { release!(new Response(JSON.stringify({ events: [recorded], total: 1 }))); });
  expect(within(row).getByText(status)).toBeInTheDocument();
  expect(within(screen.getByRole("dialog")).getByText(status)).toBeInTheDocument();
});

// Controlled synthetic proposal: validates review UI, not physical vehicle motion.
it.each(["Verify", "Dismiss"])("can view and %s a stopped-vehicle proposal and reload its saved state", async (action) => {
  const mock = backend(); const original = mock.getMockImplementation()!;
  let stored: TrafficEvent = {
    ...live, event_type: "STOPPED_VEHICLE", explanation: "SYNTHETIC stopped-vehicle regression",
    details: {
      track_id: 1, stationary_duration_seconds: 8, movement_value: 0,
      pixel_speed_debug: 0, roi_status: "INSIDE", movement_state: "STATIONARY",
      was_previously_moving: true,
    },
  };
  mock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/events") return new Response(JSON.stringify({ events: [stored], total: 1 }));
    if (url === `/api/events/live-uuid/${action.toLowerCase()}`) {
      stored = { ...stored, status: action === "Verify" ? "VERIFIED" : "DISMISSED" };
      return new Response(JSON.stringify(stored));
    }
    return original(input, init);
  });
  const page = render(<IncidentsPage auth={auth("EMPLOYEE")} />);
  const label = await screen.findByText("LIVE · DVR Camera 3");
  fireEvent.click(within(label.closest("article")!).getByRole("button", { name: "View" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("8.0s")).toBeInTheDocument();
  expect(within(dialog).getByText("INSIDE")).toBeInTheDocument();
  expect(within(dialog).getByRole("img")).toHaveAttribute("src", "/evidence/live-cameras/camera-3/live.jpg");
  fireEvent.click(within(dialog).getByRole("button", { name: action === "Verify" ? "Verify event" : "Dismiss" }));
  await waitFor(() => expect(within(dialog).getByText(stored.status)).toHaveTextContent(action === "Verify" ? "VERIFIED" : "DISMISSED"));
  page.unmount(); render(<IncidentsPage auth={auth("EMPLOYEE")} />);
  const restored = await screen.findByText("LIVE · DVR Camera 3");
  expect(within(restored.closest("article")!).getByText(stored.status)).toBeInTheDocument();
});
