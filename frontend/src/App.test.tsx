import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
  last_frame: 377,
  total_track_records: 48,
  annotated_video_available: true,
  message: "Summary calculated from the real tracks.csv output.",
};

const readyTimeline = {
  status: "READY",
  frames: [
    { frame: 1, timestamp_sec: 0.1, active_vehicle_count: 1, cars: 1, buses: 0, trucks: 0, motorcycles: 0 },
    { frame: 10, timestamp_sec: 1.0, active_vehicle_count: 3, cars: 1, buses: 0, trucks: 1, motorcycles: 1 },
  ],
  message: "Timeline calculated from real YOLO and ByteTrack output.",
};

function mockBackend(events = [proposedEvent], summary = readySummary) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input);
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
    expect(screen.getByRole("heading", { name: /traffic monitoring dashboard/i })).toBeInTheDocument();
    await screen.findByText(/press play to synchronize/i);
    playAt(1);
    expect(await screen.findByText("WRONG_WAY")).toBeInTheDocument();
    expect(screen.getByText(/real precomputed ai output/i)).toBeInTheDocument();
    expect(screen.queryByText(/fixture data/i)).not.toBeInTheDocument();
  });

  it("records a Verify decision through the Backend", async () => {
    const fetchMock = mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/press play to synchronize/i);
    playAt(1);
    fireEvent.click(await screen.findByRole("button", { name: "Verify" }));
    await waitFor(() => expect(screen.getByText("Municipal decision recorded: VERIFIED")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenLastCalledWith("/api/scenarios/normal_traffic/events/event-1/verify", { method: "POST" });
  });

  it("shows an honest empty state", async () => {
    mockBackend([]);
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    await screen.findByText(/press play to synchronize/i);
    playAt(1);
    expect(await screen.findByText("No AI event has occurred at this video time.")).toBeInTheDocument();
  });

  it("synchronizes real vehicle classes with video playback", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    const metrics = await screen.findByRole("region", { name: "Current traffic summary" });
    expect(within(metrics).getByText("Active tracked").parentElement).toHaveTextContent("0");
    playAt(1);
    expect(within(metrics).getByText("Active tracked").parentElement).toHaveTextContent("3");
    expect(within(metrics).getByText("Trucks").parentElement).toHaveTextContent("1");
    expect(within(metrics).getByText("Motorcycles").parentElement).toHaveTextContent("1");
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
    expect(within(metrics).getByText("Active tracked").parentElement).toHaveTextContent("0");
  });

  it("shows a truthful Citizen Map placeholder", () => {
    render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Citizen Traffic Map" })).toBeInTheDocument();
    expect(screen.getByText(/not implemented in this task/i)).toBeInTheDocument();
  });
});
