import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveMjpegImage } from "./LiveMjpegImage";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function streamImage() {
  return screen.getByRole("img", { name: "Camera feed" });
}

describe("LiveMjpegImage", () => {
  it("uses the unchanged MJPEG URL initially", () => {
    render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("uses the real annotated stream for AI view", () => {
    render(<LiveMjpegImage cameraId="camera-3" mode="ai" alt="Camera feed" />);
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3.mjpg");
  });

  it("enters reconnecting state and reopens the URL with a retry token", () => {
    vi.useFakeTimers();
    render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    fireEvent.error(streamImage());
    expect(screen.getByRole("status")).toHaveTextContent("Visual stream: RECONNECTING");
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg");
    act(() => vi.advanceTimersByTime(500));
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg?retry=1");
  });

  it("uses bounded backoff and exposes manual recovery after the retry limit", () => {
    vi.useFakeTimers();
    render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    for (const delay of [500, 1_000, 2_000]) {
      fireEvent.error(streamImage());
      act(() => vi.advanceTimersByTime(delay));
    }
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg?retry=3");
    fireEvent.error(streamImage());
    expect(screen.getByRole("status")).toHaveTextContent("Visual stream: ERROR");
    expect(screen.getByRole("button", { name: "Reconnect stream" })).toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears reconnecting state after a successful image load", () => {
    vi.useFakeTimers();
    render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    fireEvent.error(streamImage());
    act(() => vi.advanceTimersByTime(500));
    fireEvent.load(streamImage());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg?retry=1");
  });

  it("resets retry state when switching cameras", () => {
    vi.useFakeTimers();
    const { rerender } = render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    fireEvent.error(streamImage());
    act(() => vi.advanceTimersByTime(500));
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-3/preview.mjpg?retry=1");
    rerender(<LiveMjpegImage cameraId="camera-5" alt="Camera feed" />);
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-5/preview.mjpg");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("prevents an old camera retry timer from changing the new stream", () => {
    vi.useFakeTimers();
    const { rerender } = render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    fireEvent.error(streamImage());
    rerender(<LiveMjpegImage cameraId="camera-7" alt="Camera feed" />);
    act(() => vi.advanceTimersByTime(5_000));
    expect(streamImage()).toHaveAttribute("src", "/media/live-cameras/camera-7/preview.mjpg");
  });

  it("cancels a pending retry when unmounted", () => {
    vi.useFakeTimers();
    const { unmount } = render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
    fireEvent.error(streamImage());
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

it.each(["live", "ai"] as const)("%s gets a fresh retry budget after recovery", mode => {
  vi.useFakeTimers();
  render(<LiveMjpegImage cameraId="camera-3" mode={mode} alt="Camera feed" />);
  for (let episode = 0; episode < 5; episode++) {
    fireEvent.error(streamImage());
    expect(screen.getByRole("status")).toHaveTextContent("RECONNECTING");
    act(() => vi.advanceTimersByTime(500));
    expect(streamImage().getAttribute("src")).toContain(`retry=${episode + 1}`);
    fireEvent.load(streamImage());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  }
});

it("manual reconnect resets the automatic retry budget", () => {
  vi.useFakeTimers();
  render(<LiveMjpegImage cameraId="camera-3" alt="Camera feed" />);
  for (const delay of [500, 1000, 2000]) { fireEvent.error(streamImage()); act(() => vi.advanceTimersByTime(delay)); }
  fireEvent.error(streamImage());
  fireEvent.click(screen.getByRole("button", { name: "Reconnect stream" }));
  fireEvent.error(streamImage());
  expect(screen.getByRole("status")).toHaveTextContent("RECONNECTING");
  act(() => vi.advanceTimersByTime(500));
  expect(streamImage().getAttribute("src")).toContain("retry=5");
});
