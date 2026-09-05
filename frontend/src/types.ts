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
  current_people_count: number | null;
  last_frame: number | null;
  total_track_records: number;
  annotated_video_available: boolean;
  message: string;
};

export type AnalysisFrame = {
  frame: number;
  timestamp_sec: number;
  active_vehicle_count: number;
  cars: number;
  buses: number;
  trucks: number;
  motorcycles: number;
  people: number;
  people_in_road: number;
  tracked_people: number;
};

export type AnalysisTimeline = {
  status: "READY" | "MISSING" | "INVALID";
  frames: AnalysisFrame[];
  message: string;
};

export type ScenarioId = "normal_traffic" | "congestion" | "stopped_vehicle" | "rainy_traffic";

export type ScenarioInfo = {
  scenario_id: ScenarioId;
  title: string;
  description: string;
  expected_event: TrafficEvent["event_type"] | null;
  source_url: string;
};
