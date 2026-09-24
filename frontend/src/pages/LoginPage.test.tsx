import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthUser } from "../api/auth";
import { LoginPage } from "./LoginPage";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const user: AuthUser = { user_id: "verified-user", username: "staff@city.test", role: "ADMIN" };
function harness(reduced = false) {
  vi.stubGlobal("matchMedia", vi.fn((query: string) => ({ matches: reduced && query.includes("reduced-motion"), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  let finish: (success: boolean) => void = () => {};
  const response = new Promise<boolean>(resolve => { finish = resolve; });
  const request = vi.fn(() => response);
  function Host() {
    const [current, setCurrent] = useState<AuthUser | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    return <Routes><Route path="/login" element={<LoginPage auth={{ user: current, loading, error, initialized: true, authRequired: true, logout: async () => {}, login: async () => {
      setLoading(true); const success = await request(); setLoading(false);
      if (success) setCurrent(user); else setError("Invalid username or password");
      return success;
    } }} />} /><Route path="/command-center" element={<h1>Protected command center</h1>} /></Routes>;
  }
  const view = render(<MemoryRouter initialEntries={["/login"]}><Host /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Username or email"), { target: { value: user.username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
  const submit = () => fireEvent.submit(screen.getByLabelText("Username or email").closest("form")!);
  return { finish, request, submit, ...view };
}

describe("CityEye authentication motion", () => {
  it("never claims success before confirmation and transitions within 720ms afterwards", async () => {
    vi.useFakeTimers(); const test = harness();
    test.submit(); test.submit();
    expect(test.request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Verifying access");
    await act(async () => vi.advanceTimersByTime(2000));
    expect(screen.queryByText("Identity verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Protected command center")).not.toBeInTheDocument();
    await act(async () => test.finish(true));
    expect(screen.getByRole("status")).toHaveTextContent("Identity verified");
    await act(async () => vi.advanceTimersByTime(260));
    expect(screen.getByRole("status")).toHaveTextContent("Access granted");
    await act(async () => vi.advanceTimersByTime(460));
    expect(screen.getByText("Protected command center")).toBeInTheDocument();
  });

  it("shows a restrained failure and permits another attempt without navigation", async () => {
    vi.useFakeTimers(); const test = harness(); test.submit();
    await act(async () => test.finish(false));
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(screen.getByRole("status")).toHaveTextContent("Access not verified");
    expect(screen.getByRole("button", { name: "Enter command center" })).toBeEnabled();
    await act(async () => vi.advanceTimersByTime(1200));
    expect(screen.queryByText("Protected command center")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Username or email")).toHaveValue(user.username);
  });

  it("skips the success delay for reduced motion", async () => {
    const test = harness(true); test.submit(); await act(async () => test.finish(true));
    expect(screen.getByText("Protected command center")).toBeInTheDocument();
  });

  it("cleans up a pending success transition on unmount", async () => {
    vi.useFakeTimers(); const test = harness(); test.submit();
    await act(async () => test.finish(true)); test.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
