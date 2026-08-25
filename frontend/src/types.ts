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

export type AnalysisSummary = {
  status: "READY" | "MISSING" | "INVALID";
  current_vehicle_count: number | null;
  last_frame: number | null;
  total_track_records: number;
  annotated_video_available: boolean;
  message: string;
};
