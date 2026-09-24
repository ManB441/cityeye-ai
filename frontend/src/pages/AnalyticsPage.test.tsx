import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AnalyticsPage } from "./AnalyticsPage";

const data = {
  camera_id: "camera-3", requested_start: 0, requested_end: 1200,
  data_since: 10, first_sample_at: 10, latest_sample_at: 910,
  sampling_interval_seconds: 60, bucket_seconds: 300, samples: 3,
  average_vehicles_observed: 4, peak_vehicle_count: 8, peak_period_start: 900,
  peak_period_end: 1200, congestion_episodes: 0, congestion_duration_minutes: 0,
  incident_count: 0, average_capture_fps: 10, average_ai_fps: 3, observed_minutes: 3,
  vehicle_composition_observations: { cars: 12 }, incidents_by_type: {}, incidents_by_status: {},
  traffic_status_samples: { UNKNOWN: 3 },
  traffic_series: [0, 300, 900].map(timestamp => ({ timestamp, average_vehicles_observed: 4,
    peak_vehicles_observed: 4, samples: 1, traffic_status: "UNKNOWN" })),
};
function backend(payload = data) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async input => {
    if (String(input) === "/api/live-cameras") return new Response(JSON.stringify([{ camera_id: "camera-3" }, { camera_id: "camera-5" }]));
    return new Response(JSON.stringify(payload));
  });
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("positions samples by real time without bridging unobserved periods", async () => {
  backend(); render(<AnalyticsPage />);
  const chart = await screen.findByRole("img", { name: "Average vehicles observed by time bucket" });
  expect([...chart.querySelectorAll("circle")].map(p => Number(p.getAttribute("cx")))).toEqual([0, 25, 75]);
  expect(chart.querySelector("polyline")).toBeNull();
});

it("shows unknown traffic and missing recent samples without claiming continuous coverage", async () => {
  backend(); render(<AnalyticsPage />);
  expect(await screen.findByText("Traffic classification unavailable")).toBeInTheDocument();
  expect(screen.getByText(/No recent samples/)).toBeInTheDocument();
  expect(screen.queryByText("No congestion recorded")).not.toBeInTheDocument();
  expect(screen.getByText(/3.0 sample-equivalent minutes/)).toBeInTheDocument();
});

it("distinguishes moderate, heavy, and unknown observations", async () => {
  backend({ ...data, traffic_status_samples: { MODERATE: 1, HEAVY_CONGESTION: 1, UNKNOWN: 1 } } as typeof data);
  render(<AnalyticsPage />);
  expect(await screen.findByText("Moderate: 1 · Heavy: 1 · Unknown: 1")).toBeInTheDocument();
});

it("does not retain the previous camera values after a failed selection and supports retry", async () => {
  const fetch = backend(); render(<AnalyticsPage />);
  await screen.findByText("Observed detection share");
  fetch.mockImplementation(async () => new Response("{}", { status: 500 }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "camera-5" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 500");
  expect(screen.queryByText("Observed detection share")).not.toBeInTheDocument();
  fetch.mockImplementation(async () => new Response(JSON.stringify({ ...data, camera_id: "camera-5" })));
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Observed detection share")).toBeInTheDocument();
});
