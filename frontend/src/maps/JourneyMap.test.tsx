import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { JourneyMap } from "./JourneyMap";
vi.mock("./GoogleTrafficMap", () => ({ GoogleTrafficMap: ({ origin, onPick }: any) => <button onClick={() => onPick({ lat: 31.5, lng: 35.2 })}>Map at {origin?.lat ?? "default"}</button> }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("requests location only after the user activates the compact prompt, then closes it", () => {
  const getCurrentPosition = vi.fn(success => success({ coords: { latitude: 31.9, longitude: 35.1, accuracy: 20 } }));
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });
  render(<JourneyMap features={[]} onSelect={() => {}} />);
  expect(getCurrentPosition).not.toHaveBeenCalled();
  expect(screen.getByText("Map at default")).toBeInTheDocument();
  expect(screen.getByText("حدد موقعك لعرض المعلومات القريبة منك")).toBeInTheDocument();
  fireEvent.click(screen.getByText("تحديد موقعي"));
  expect(screen.getByText("Map at 31.9")).toBeInTheDocument();
  expect(screen.queryByText("حدد موقعك لعرض المعلومات القريبة منك")).toBeNull();
  expect(screen.getByLabelText("إلى أين تريد الذهاب؟")).toBeInTheDocument();
});
it("keeps a compact retry prompt when device permission is denied", () => {
  vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: (_ok: unknown, fail: any) => fail({ code: 1 }) } });
  render(<JourneyMap features={[]} onSelect={() => {}} />);
  fireEvent.click(screen.getByText("تحديد موقعي"));
  expect(screen.getByRole("alert")).toHaveTextContent("نحتاج إلى إذن الموقع");
  expect(screen.getByText("حاول مرة أخرى")).toBeInTheDocument();
  expect(screen.queryByRole("spinbutton")).toBeNull();
  expect(screen.getByText("Map at default")).toBeInTheDocument();
});
