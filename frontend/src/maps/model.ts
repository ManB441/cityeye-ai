export type MapKind = "camera" | "road" | "incident" | "report";
export type MapFeature = {
  type: "Feature"; id: string;
  geometry: { type: "Point"; coordinates: [number, number] } | { type: "LineString"; coordinates: [number, number][] };
  properties: { id: string; kind: MapKind; label: string; status: string; observed_at?: number | null;
    valid_for_seconds?: number; location_accuracy: string; description?: string; vehicles?: number | null };
};
export type MapSnapshot = { type: "FeatureCollection"; features: MapFeature[]; generated_at: number;
  scope: "PUBLIC" | "OPERATIONS"; configured_cameras: number; notice: string };
export const COLORS = { NORMAL: "#25a56a", MODERATE: "#e9ae35", HEAVY_CONGESTION: "#ef5350", UNKNOWN: "#8796a5",
  VERIFIED: "#d34fff", PROPOSED: "#f39c36", PENDING: "#4f95ff", COMMUNITY_CONFIRMED: "#5271db", FRESH: "#33b8c8" };
export function featureColor(feature: MapFeature): string {
  return COLORS[feature.properties.status as keyof typeof COLORS] ?? COLORS.UNKNOWN;
}
export function expireFeatures(snapshot: MapSnapshot, elapsedSeconds: number): MapFeature[] {
  return snapshot.features.map(feature => {
    if (!["road", "camera"].includes(feature.properties.kind) || elapsedSeconds < (feature.properties.valid_for_seconds ?? 0)) return feature;
    return { ...feature, properties: { ...feature.properties, status: "UNKNOWN", vehicles: null } };
  });
}
