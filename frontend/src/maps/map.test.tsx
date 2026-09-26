import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GoogleTrafficMap } from "./GoogleTrafficMap";
import { expireFeatures, type MapSnapshot } from "./model";
import { CitizenMapPage } from "../pages/CitizenMapPage";

const snapshot: MapSnapshot = { type: "FeatureCollection", generated_at: 100, scope: "OPERATIONS", configured_cameras: 1, notice: "Confirmed coverage only",
  features: [{ type: "Feature", id: "road", geometry: { type: "LineString", coordinates: [[35, 31], [35.001, 31.001]] },
    properties: { id: "road", kind: "road", label: "Test road", status: "NORMAL", valid_for_seconds: 2, location_accuracy: "MONITORED_SEGMENT" } }] };
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs(); vi.useRealTimers(); });

it("does not contact Google before a key is configured", () => {
  render(<GoogleTrafficMap features={[]} onSelect={() => {}} apiKey="" />);
  expect(screen.getByText("Google Maps setup required")).toBeInTheDocument();
  expect(document.querySelector('script[src*="maps.googleapis.com"]')).toBeNull();
});

it("expires road conditions instead of retaining green when polling stalls", () => {
  expect(expireFeatures(snapshot, 1)[0].properties.status).toBe("NORMAL");
  expect(expireFeatures(snapshot, 2)[0].properties.status).toBe("UNKNOWN");
});

it("filters geographic layers and shows textual details without a Google key", async () => {
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(snapshot)));
  render(<CitizenMapPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Test road/ }));
  expect(screen.getByRole("region", { name: "Selected map observation" })).toHaveTextContent("MONITORED SEGMENT");
  fireEvent.click(screen.getByRole("button", { name: "الطبقات" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Road conditions" }));
  expect(screen.queryByRole("button", { name: /Test road/ })).not.toBeInTheDocument();
});

it("clears observations after API failure instead of displaying stale road state", async () => {
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "");
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify(snapshot)));
  render(<CitizenMapPage />);
  await screen.findByRole("button", { name: /Test road/ });
  fetch.mockImplementation(async () => new Response("{}", { status: 503 }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("تعذر تحديث بيانات CityEye"), { timeout: 4500 });
  expect(screen.queryByRole("button", { name: /Test road/ })).not.toBeInTheDocument();
});

it("loads the SDK only once and replaces map data without reloading the base map", async () => {
  let callback: ((event: { feature: { getProperty: () => string } }) => void) | undefined;
  const removed = vi.fn();
  const addGeoJson = vi.fn();
  const Map = vi.fn(function () { return { data: { addGeoJson, forEach: vi.fn(), remove: vi.fn(), setStyle: vi.fn(),
    addListener: (_name: string, cb: typeof callback) => { callback = cb; return { remove: removed }; } }, setCenter: vi.fn(), setZoom: vi.fn(), addListener: vi.fn(), fitBounds: vi.fn() }; });
  window.google = { maps: { Map, Polyline: vi.fn(function () { return { setMap: vi.fn() }; }), Marker: vi.fn(function () { return { setMap: vi.fn() }; }), LatLngBounds: vi.fn(function () { return { extend: vi.fn() }; }), SymbolPath: { CIRCLE: 0 } } };
  const select = vi.fn();
  const view = render(<GoogleTrafficMap features={snapshot.features} onSelect={select} apiKey="synthetic-test-key" />);
  await waitFor(() => expect(addGeoJson).toHaveBeenCalled());
  view.rerender(<GoogleTrafficMap features={expireFeatures(snapshot, 3)} onSelect={select} apiKey="synthetic-test-key" />);
  expect(Map).toHaveBeenCalledTimes(1);
  act(() => callback?.({ feature: { getProperty: () => "road" } }));
  expect(select).toHaveBeenCalledWith("road");
  view.unmount(); expect(removed).toHaveBeenCalled(); delete window.google;
});
