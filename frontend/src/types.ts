export type StoppedVehicleDetails = {
  track_id: number;
  vehicle_class: string;
  stationary_duration_seconds: number;
  movement_value: number;
  movement_unit: string;
  instantaneous_normalized_movement: number;
  pixel_speed_debug: number;
  roi_status: string;
};

export type RoadBlockageDetails = {
  track_id: number;
  vehicle_class: string;
  zone_name: string;
  stationary_duration_seconds: number;
  vehicle_zone_overlap: number;
  normalized_obstruction_ratio: number;
  upstream_vehicle_count: number;
  slow_upstream_vehicle_count: number;
  traffic_impact_duration_seconds: number;
  confidence_reasoning: string;
  evidence_timestamp: number;
};

export type TrafficEvent = {
  event_id: string;
  event_type: "WRONG_WAY" | "STOPPED_VEHICLE" | "CONGESTION" | "ROAD_BLOCKAGE";
  timestamp: number;
  confidence: number;
  severity: "LOW" | "MEDIUM" | "HIGH";
  explanation: string;
  camera_name: string;
  latitude: number;
  longitude: number;
  evidence_image: string;
  status: "PROPOSED" | "VERIFIED" | "DISMISSED";
  details?: StoppedVehicleDetails | RoadBlockageDetails | null;
};

export type EventListResponse = {
  events: TrafficEvent[];
  total: number;
};

export type AnalysisSummary = {
  status: "READY" | "MISSING" | "INVALID";
  current_vehicle_count: number | null;
  current_people_count: number | null;
  current_bicycle_count: number | null;
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
  bicycles: number;
  bicycles_in_road: number;
  tracked_bicycles: number;
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

export type ScenarioSnapshot = {
  scenario: ScenarioInfo;
  summary: AnalysisSummary | null;
  events: TrafficEvent[];
  summaryError: boolean;
  eventsError: boolean;
};

export type SystemReadiness = {
  status: "ready" | "degraded" | "unavailable";
  service?: string;
  environment?: string;
  components?: Record<string, { status: string; detail?: string }>;
};

export type CitizenReport = {
  report_id: string;
  category: "CONGESTION" | "ROAD_HAZARD" | "BLOCKED_ROAD" | "OTHER";
  description: string;
  latitude: number;
  longitude: number;
  reported_at: string;
  status: "PENDING" | "COMMUNITY_CONFIRMED";
  demo_user_id: string;
};
