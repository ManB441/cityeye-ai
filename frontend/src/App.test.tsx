import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fetchSession, type SessionInfo } from "./api/auth";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

const proposedEvent = {
  event_id: "event-1",
  event_type: "WRONG_WAY",
  timestamp: 0.5,
  confidence: 0.91,
  severity: "HIGH",
  explanation: "Track moved opposite to the allowed direction.",
  camera_name: "Demo Camera 1",
  latitude: 31.95,
  longitude: 35.91,
  evidence_image: "evidence/event-1.jpg",
  status: "PROPOSED",
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const readySummary = {
  status: "READY",
  current_vehicle_count: 2,
  current_people_count: 0,
  current_bicycle_count: 0,
  last_frame: 377,
  total_track_records: 48,
  annotated_video_available: true,
  message: "Summary calculated from the real tracks.csv output.",
};

const readyTimeline = {
  status: "READY",
  frames: [
    { frame: 0, timestamp_sec: 0, active_vehicle_count: 2, cars: 2, buses: 0, trucks: 0, motorcycles: 0, people: 0, people_in_road: 0, tracked_people: 0, bicycles: 0, bicycles_in_road: 0, tracked_bicycles: 0 },
    { frame: 1, timestamp_sec: 0.1, active_vehicle_count: 1, cars: 1, buses: 0, trucks: 0, motorcycles: 0, people: 0, people_in_road: 0, tracked_people: 0, bicycles: 0, bicycles_in_road: 0, tracked_bicycles: 0 },
    { frame: 10, timestamp_sec: 1.0, active_vehicle_count: 3, cars: 1, buses: 0, trucks: 1, motorcycles: 1, people: 2, people_in_road: 1, tracked_people: 2, bicycles: 1, bicycles_in_road: 1, tracked_bicycles: 1 },
  ],
  message: "Timeline calculated from real YOLO and ByteTrack output.",
};

function mockBackend(
  events = [proposedEvent],
  summary = readySummary,
  authSession: SessionInfo = {
    auth_required: false,
    user: { user_id: "demo-access", username: "Demo Operator", role: "ADMIN" },
  },
  loginSucceeds = true,
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input);
    if (url === "/health/ready") return jsonResponse({ status: "ready", service: "cityeye-ai-backend", components: {} });
    if (url === "/api/citizen-reports") return jsonResponse({ reports: [], total: 0 });
    if (url === "/api/auth/session") return jsonResponse(authSession);
    if (url === "/api/auth/login" && options?.method === "POST" && !loginSucceeds) return jsonResponse({ detail: "Invalid username or password" }, 401);
    if (url === "/api/auth/login" && options?.method === "POST") return jsonResponse({
      access_token: "test-session-token",
      token_type: "bearer",
      expires_at: 9999999999,
      user: { user_id: "reviewer-1", username: "reviewer", role: "REVIEWER" },
    });
    if (url === "/api/scenarios") return jsonResponse({ scenarios: [
      { scenario_id: "normal_traffic", title: "Normal Traffic", description: "Free flowing", expected_event: null, source_url: "https://example.com/normal" },
      { scenario_id: "congestion", title: "Heavy Congestion", description: "Dense traffic", expected_event: "CONGESTION", source_url: "https://example.com/congestion" },
      { scenario_id: "stopped_vehicle", title: "Stopped Vehicle", description: "Disabled car", expected_event: "STOPPED_VEHICLE", source_url: "https://example.com/stopped" },
      { scenario_id: "rainy_traffic", title: "Rainy Traffic", description: "Wet-road traffic", expected_event: null, source_url: "https://example.com/rainy" },
    ] });
    if (url.endsWith("/analysis/summary")) return jsonResponse(summary);
    if (url.endsWith("/analysis/timeline")) return jsonResponse(readyTimeline);
    if (url === "/api/scenarios/normal_traffic/events/event-1/verify" && options?.method === "POST") {
      return jsonResponse({ ...proposedEvent, status: "VERIFIED" });
    }
    if (url.endsWith("/events")) return jsonResponse({ events, total: events.length });
    return jsonResponse({ detail: "Not found" }, 404);
  });
}

function playAt(seconds: number) {
  const video = screen.getByText(/browser does not support mp4/i).closest("video") as HTMLVideoElement;
  Object.defineProperty(video, "currentTime", { configurable: true, value: seconds });
  fireEvent.play(video);
  fireEvent.timeUpdate(video);
  return video;
}

describe("CityEye municipal dashboard", () => {
  it("displays real Backend events without fixture claims", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /command center/i })).toBeInTheDocument();
    await screen.findByText(/start recorded footage/i);
    playAt(1);
    expect(await screen.findByText("WRONG WAY")).toBeInTheDocument();
    expect(screen.getByText(/real video-synced data/i)).toBeInTheDocument();
    expect(screen.getAllByText("RECORDED").length).toBeGreaterThan(0);
    expect(screen.queryByText(/fixture data/i)).not.toBeInTheDocument();
  });

  it("records a Verify decision through the Backend", async () => {
    const fetchMock = mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/start recorded footage/i);
    playAt(1);
    fireEvent.click(await screen.findByRole("button", { name: "Verify" }));
    await waitFor(() => expect(screen.getByText("VERIFIED")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenLastCalledWith("/api/scenarios/normal_traffic/events/event-1/verify", { method: "POST" });
  });

  it("requires sign-in before municipal decisions and sends the bearer token", async () => {
    const fetchMock = mockBackend([proposedEvent], readySummary, {
      auth_required: true,
      user: null,
    });
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/start recorded footage/i);
    playAt(1);
    expect(await screen.findByRole("button", { name: "Verify" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /sign in required/i }));
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "reviewer" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "reviewer-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("button", { name: /reviewer reviewer/i });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/scenarios/normal_traffic/events/event-1/verify",
      { method: "POST", headers: { Authorization: "Bearer test-session-token" } },
    ));
  });

  it("keeps Operator accounts read-only for municipal decisions", async () => {
    mockBackend([proposedEvent], readySummary, {
      auth_required: true,
      user: { user_id: "operator-1", username: "operator", role: "OPERATOR" },
    });
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/start recorded footage/i);
    playAt(1);
    expect(await screen.findByRole("button", { name: "Verify" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeDisabled();
  });

  it("keeps the sign-in form open after invalid credentials", async () => {
    mockBackend([proposedEvent], readySummary, { auth_required: true, user: null }, false);
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    const accessButton = await screen.findByRole("button", { name: /sign in required/i });
    fireEvent.click(accessButton);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "reviewer" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("does not expose raw authentication API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Not Found" }, 404));
    await expect(fetchSession()).rejects.toThrow("Access service is unavailable. Operator actions are disabled.");
  });

  it("shows an honest empty state", async () => {
    mockBackend([]);
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/start recorded footage/i);
    playAt(1);
    expect(await screen.findByText("No incident at this time")).toBeInTheDocument();
  });

  it("synchronizes real vehicle classes with video playback", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    const metrics = await screen.findByRole("region", { name: "Current traffic summary" });
    expect(within(metrics).getByText("Vehicles").parentElement).toHaveTextContent("2");
    playAt(1);
    expect(within(metrics).getByText("Vehicles").parentElement).toHaveTextContent("3");
    expect(within(metrics).getByText("Trucks").parentElement).toHaveTextContent("1");
    expect(within(metrics).getByText("Motorcycles").parentElement).toHaveTextContent("1");
    expect(within(metrics).getByText("People").parentElement).toHaveTextContent("2");
    expect(within(metrics).getByText("Bicycles").parentElement).toHaveTextContent("1");
    const video = screen.getByText(/browser does not support mp4/i).closest("video");
    expect(video).toHaveAttribute("src", "/media/scenarios/normal_traffic/annotated.mp4");
  });

  it("switches between all real scenarios and resets playback metrics", async () => {
    const fetchMock = mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /heavy congestion/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/scenarios/congestion/analysis/summary", expect.any(Object),
    ));
    const video = screen.getByText(/browser does not support mp4/i).closest("video");
    expect(video).toHaveAttribute("src", "/media/scenarios/congestion/annotated.mp4");
    playAt(1);
    fireEvent.click(screen.getByRole("button", { name: /rainy traffic/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/scenarios/rainy_traffic/analysis/summary", expect.any(Object),
    ));
    const rainyVideo = screen.getByText(/browser does not support mp4/i).closest("video");
    expect(rainyVideo).toHaveAttribute("src", "/media/scenarios/rainy_traffic/annotated.mp4");
    const metrics = screen.getByRole("region", { name: "Current traffic summary" });
    expect(within(metrics).getByText("Vehicles").parentElement).toHaveTextContent("2");
  });

  it("shows a truthful Citizen Map placeholder", () => {
    render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Citizen Map" })).toBeInTheDocument();
    expect(screen.getAllByText("NOT YET AVAILABLE").length).toBeGreaterThan(0);
  });

  it("shows only real configured camera sources", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/cameras"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Cameras & Video Sources" })).toBeInTheDocument();
    expect(await screen.findByText("DEMO-04")).toBeInTheDocument();
    expect(screen.queryByText("CAM-04")).not.toBeInTheDocument();
    expect(screen.getByText(/no live rtsp camera is configured/i)).toBeInTheDocument();
  });

  it("reports legacy API health as readiness unknown instead of unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/health/ready") return jsonResponse({ detail: "Not Found" }, 404);
      if (url === "/health") return jsonResponse({ status: "ok", service: "cityeye-ai-backend" });
      if (url === "/api/auth/session") return jsonResponse({ auth_required: false, user: { user_id: "demo", username: "Demo Operator", role: "ADMIN" } });
      if (url === "/api/scenarios") return jsonResponse({ scenarios: [] });
      if (url === "/api/citizen-reports") return jsonResponse({ reports: [], total: 0 });
      return jsonResponse({ detail: "Not Found" }, 404);
    });
    render(<MemoryRouter initialEntries={["/analytics"]}><App /></MemoryRouter>);
    expect(await screen.findByText("API ONLINE · READINESS UNKNOWN")).toBeInTheDocument();
  });

  it("marks unsupported analytics as future instead of showing fake metrics", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/analytics"]}><App /></MemoryRouter>);
    expect(await screen.findByText("DATA COLLECTION REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("CALIBRATION REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("FUTURE / DATA COLLECTION")).toBeInTheDocument();
    expect(screen.queryByText("18,462")).not.toBeInTheDocument();
  });

  it("renders measured road blockage evidence in the existing incident workflow", async () => {
    const roadBlockage = {
      ...proposedEvent,
      event_type: "ROAD_BLOCKAGE",
      explanation: "Vehicle #42 remained stationary inside Main Lane for 8.4 seconds.",
      details: {
        track_id: 42, vehicle_class: "car", zone_name: "Main Lane",
        stationary_duration_seconds: 8.4, vehicle_zone_overlap: 0.72,
        normalized_obstruction_ratio: 0.18, upstream_vehicle_count: 3,
        slow_upstream_vehicle_count: 2,
        traffic_impact_duration_seconds: 1.0,
        confidence_reasoning: "stationary vehicle overlaps active blockage zone; 2 slow upstream vehicles",
        evidence_timestamp: 8.4,
      },
    };
    mockBackend([roadBlockage]);
    render(<MemoryRouter initialEntries={["/incidents"]}><App /></MemoryRouter>);
    fireEvent.click((await screen.findAllByRole("button", { name: "View" }))[0]);
    expect(await screen.findByText("Main Lane")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("2", { selector: "dd" })).toBeInTheDocument();
  });
});
