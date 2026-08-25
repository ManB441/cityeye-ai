import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";

afterEach(cleanup);

describe("CityEye frontend skeleton", () => {
  it("labels dashboard fixture data honestly", () => {
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /traffic monitoring dashboard/i })).toBeInTheDocument();
    expect(screen.getByText("FIXTURE DATA — NOT AI OUTPUT")).toBeInTheDocument();
    expect(screen.getByText("WRONG_WAY")).toBeInTheDocument();
  });

  it("keeps review actions disabled before Backend integration", () => {
    render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Verify" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeDisabled();
  });

  it("shows a truthful Citizen Map placeholder", () => {
    render(<MemoryRouter initialEntries={["/map"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Citizen Traffic Map" })).toBeInTheDocument();
    expect(screen.getByText(/not implemented in this task/i)).toBeInTheDocument();
  });
});
