export type TrafficEvent = {
  event_id: string;
  event_type: "WRONG_WAY" | "STOPPED_VEHICLE" | "CONGESTION";
  timestamp: number;
  confidence: number;
  severity: "LOW" | "MEDIUM" | "HIGH";
  explanation: string;
  camera_name: string;
  latitude: number;
  longitude: number;
  evidence_image: string;
  status: "PROPOSED" | "VERIFIED" | "DISMISSED";
};

export type EventListResponse = {
  events: TrafficEvent[];
  total: number;
};
