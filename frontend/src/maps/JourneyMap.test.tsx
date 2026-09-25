import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { JourneyMap } from "./JourneyMap";
vi.mock("./GoogleTrafficMap", () => ({ GoogleTrafficMap: ({ origin, onPick }: any) => <button onClick={() => onPick({ lat: 31.5, lng: 35.2 })}>Map at {origin.lat}</button> }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("requests location only after consent and prompts for destination", () => {
  const getCurrentPosition = vi.fn(success => success({ coords: { latitude: 31.9, longitude: 35.1, accuracy: 20 } }));
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });
  render(<JourneyMap features={[]} onSelect={() => {}} />);
  expect(getCurrentPosition).not.toHaveBeenCalled();
  expect(screen.queryByText(/Map at/)).toBeNull();
  fireEvent.click(screen.getByText("تحديد موقعي من الجهاز"));
  expect(screen.getByText("Map at 31.9")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Map at 31.9"));
  expect(screen.getByText(/تم تحديد وجهتك على الخريطة/)).toBeInTheDocument();
});
it("explains denied device permission without asking for coordinates", () => {
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: (_ok: unknown, fail: any) => fail({ code: 1 }) } });
  render(<JourneyMap features={[]} onSelect={() => {}} />);
  fireEvent.click(screen.getByText("تحديد موقعي من الجهاز"));
  expect(screen.getByRole("status")).toHaveTextContent("محظور");
  expect(screen.getByText("السماح باستخدام الموقع")).toBeInTheDocument();
  expect(screen.queryByRole("spinbutton")).toBeNull();
  expect(screen.queryByText(/Map at/)).toBeNull();
});
