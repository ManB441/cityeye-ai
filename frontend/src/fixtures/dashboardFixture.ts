import type { FixtureEvent } from "../types";

// Layout-only fixture. This data is not produced by the AI pipeline.
export const dashboardFixture = {
  cameraName: "Demo Camera 1",
  vehicleCount: 12,
  trafficStatus: "Moderate",
  events: [
    {
      eventId: "fixture-event-1",
      eventType: "WRONG_WAY",
      timestamp: "Demo time 10:30:00",
      confidence: 0.86,
      severity: "HIGH",
      explanation: "Fixture explanation for dashboard layout only.",
    },
  ] satisfies FixtureEvent[],
};
