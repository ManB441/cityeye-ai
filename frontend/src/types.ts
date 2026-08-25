export type FixtureEvent = {
  eventId: string;
  eventType: "WRONG_WAY" | "STOPPED_VEHICLE" | "CONGESTION";
  timestamp: string;
  confidence: number;
  severity: "LOW" | "MEDIUM" | "HIGH";
  explanation: string;
};
