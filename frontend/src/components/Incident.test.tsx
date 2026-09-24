import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IncidentDetail } from "./Incident";
import type { TrafficEvent } from "../types";
afterEach(cleanup);
const event = { event_id: "1", event_type: "CONGESTION", severity: "HIGH", status: "VERIFIED", timestamp: 1, confidence: .9, camera_name: "Test", explanation: "Test", evidence_image: "test.jpg" } as TrafficEvent;
it("uses the saved review banner and provides an evidence failure fallback", () => {
  render(<IncidentDetail event={event} canReview reviewing={false} onClose={vi.fn()} onDecision={vi.fn()} />);
  expect(screen.queryByText("AI PROPOSED EVENT")).not.toBeInTheDocument();
  expect(screen.getByText("MUNICIPAL DECISION: VERIFIED")).toBeInTheDocument();
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("status")).toHaveTextContent("Evidence image is unavailable");
});
it("traps Tab, closes with Escape and restores the opener's focus", () => {
  const opener = document.createElement("button"); document.body.appendChild(opener); opener.focus();
  const onClose = vi.fn();
  const view = render(<IncidentDetail event={{ ...event, status: "PROPOSED" }} canReview reviewing={false} onClose={onClose} onDecision={vi.fn()} />);
  const dialog = screen.getByRole("dialog");
  const close = within(dialog).getByRole("button", { name: "Close incident detail" });
  const last = within(dialog).getByRole("button", { name: "Dismiss" });
  expect(close).toHaveFocus();
  fireEvent.keyDown(close, { key: "Tab", shiftKey: true }); expect(last).toHaveFocus();
  fireEvent.keyDown(last, { key: "Tab" }); expect(close).toHaveFocus();
  fireEvent.keyDown(close, { key: "Escape" }); expect(onClose).toHaveBeenCalledOnce();
  view.unmount(); expect(opener).toHaveFocus(); opener.remove();
});
