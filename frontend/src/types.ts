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
  source_type?: "LIVE_CAMERA" | "RECORDED_SCENARIO";
  source_id?: string;
  details?: StoppedVehicleDetails | RoadBlockageDetails | Record<string, unknown> | null;
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
  traffic_state: string;
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

export type ScenarioId =
  | "normal_traffic"
  | "congestion"
  | "stopped_vehicle"
  | "rainy_traffic"
  | "maydan_palestine";

export type ScenarioInfo = {
  scenario_id: ScenarioId;
  title: string;
  description: string;
  expected_event: TrafficEvent["event_type"] | null;
  source_url: string;
};

export type CameraHealth = {
  camera_id: string;
  source_type: "RTSP";
  state: "ONLINE" | "STALE" | "OFFLINE" | "RECONNECTING";
  last_frame_at: number | null;
  last_connected_at: number | null;
  last_error: string | null;
  processing_fps: number;
  ai_inference_fps: number;
  reconnect_attempts: number;
  generation: number;
  dropped_frames: number;
  heartbeat_at: number | null;
  last_visual_change_at: number | null;
  callback_sequence: number;
  visual_sequence: number;
  consecutive_similar_frames: number;
  camera_capture_fps: number;
  preview_publication_fps: number;
  preview_last_frame_at: number | null;
  buffer_pressure: number;
  checked_at: number;
  valid_for_seconds: number;
  expires_at?: number;
};

export type LiveMetrics = {
  frame: number;
  timestamp: number;
  generation: number;
  current_detection_count: number;
  active_vehicle_count: number;
  active_track_count: number;
  cars: number;
  buses: number;
  trucks: number;
  motorcycles: number;
  people: number;
  bicycles: number;
  traffic_state: string;
  moving_vehicles: number;
  stationary_vehicles: number;
  unknown_movement_vehicles: number;
};

export type LiveMetricsSnapshot = {
  camera_id: string;
  checked_at: number;
  max_age_seconds: number;
  valid_for_seconds: number;
  reason:
    | "FRESH"
    | "MISSING"
    | "INVALID"
    | "STALE"
    | "OFFLINE"
    | "SOURCE_MISMATCH"
    | "GENERATION_MISMATCH";
  health: CameraHealth;
  metrics: LiveMetrics | null;
  expires_at: number;
};

export type AnalyticsSeriesPoint = {
  timestamp: number;
  average_vehicles_observed: number;
  peak_vehicles_observed: number;
  samples: number;
  traffic_status: string;
};

export type OperationalAnalytics = {
  camera_id: string;
  requested_start: number;
  requested_end: number;
  data_since: number | null;
  first_sample_at: number | null;
  latest_sample_at: number | null;
  sampling_interval_seconds: number;
  bucket_seconds: number;
  samples: number;
  average_vehicles_observed: number | null;
  peak_vehicle_count: number | null;
  peak_period_start: number | null;
  peak_period_end: number | null;
  congestion_episodes: number;
  congestion_duration_minutes: number;
  incident_count: number;
  average_capture_fps: number | null;
  average_ai_fps: number | null;
  observed_minutes: number;
  vehicle_composition_observations: Record<string, number>;
  incidents_by_type: Record<string, number>;
  incidents_by_status: Record<string, number>;
  traffic_series: AnalyticsSeriesPoint[];
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