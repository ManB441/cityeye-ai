import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  timestamp: 12.5,
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

function mockBackend(events = [proposedEvent], summary = readySummary) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input);
    if (url === "/api/analysis/summary") return jsonResponse(summary);
    if (url === "/api/events/event-1/verify" && options?.method === "POST") {
      return jsonResponse({ ...proposedEvent, status: "VERIFIED" });
    }
    if (url === "/api/events") return jsonResponse({ events, total: events.length });
    return jsonResponse({ detail: "Not found" }, 404);
  });
}

describe("CityEye municipal dashboard", () => {
  it("displays real Backend events without fixture claims", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /traffic monitoring dashboard/i })).toBeInTheDocument();
    expect(await screen.findByText("WRONG_WAY")).toBeInTheDocument();
    expect(screen.getByText(/live backend data/i)).toBeInTheDocument();
    expect(screen.queryByText(/fixture data/i)).not.toBeInTheDocument();
  });

  it("records a Verify decision through the Backend", async () => {
    const fetchMock = mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Verify" }));
    await waitFor(() => expect(screen.getByText("Municipal decision recorded: VERIFIED")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenLastCalledWith("/api/events/event-1/verify", { method: "POST" });
  });

  it("shows an honest empty state", async () => {
    mockBackend([]);
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(await screen.findByText("No AI events have been stored yet.")).toBeInTheDocument();
  });

  it("shows real vehicle count and annotated video availability", async () => {
    mockBackend();
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(await screen.findByText("2")).toBeInTheDocument();
    const video = screen.getByText(/browser does not support mp4/i).closest("video");
    expect(video).toHaveAttribute("src", "/media/annotated.mp4");
  });

  it("shows a truthful Citizen Map placeholder", () => {
    render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Citizen Traffic Map" })).toBeInTheDocument();
    expect(screen.getByText(/not implemented in this task/i)).toBeInTheDocument();
  });
});
