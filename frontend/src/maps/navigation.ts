import type { MapFeature } from "./model";
import type { Position, RouteOption, RouteStep } from "./google";

const EARTH_RADIUS_METERS = 6_371_000;
export function metersBetween(a: Position, b: Position): number {
  const radians = (value: number) => value * Math.PI / 180;
  const dLat = radians(b.lat - a.lat), dLng = radians(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(a.lat)) * Math.cos(radians(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(h));
}
export function nearestRoutePoint(path: Position[], position: Position): { index: number; distanceMeters: number } {
  return path.reduce((best, point, index) => {
    const distanceMeters = metersBetween(position, point);
    return distanceMeters < best.distanceMeters ? { index, distanceMeters } : best;
  }, { index: 0, distanceMeters: Number.POSITIVE_INFINITY });
}
export function remainingDistance(route: RouteOption, pathIndex: number): number {
  const remaining = route.path.slice(Math.max(0, pathIndex));
  return remaining.slice(1).reduce((sum, point, index) => sum + metersBetween(remaining[index], point), 0);
}
export function nextRouteStep(route: RouteOption, position: Position): RouteStep | undefined {
  return route.steps.find(step => metersBetween(position, step.end) > 15);
}
export function routeRelevantFeatures(features: MapFeature[], path: Position[], radiusMeters = 150): MapFeature[] {
  return features.filter(feature => {
    const coordinates = feature.geometry.type === "Point" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    return coordinates.some(([lng, lat]) => nearestRoutePoint(path, { lat, lng }).distanceMeters <= radiusMeters);
  });
}
export function humanDistance(meters: number): string { return meters >= 1000 ? `${(meters / 1000).toFixed(1)} كم` : `${Math.max(0, Math.round(meters))} م`; }
export function humanDuration(seconds: number): string { return seconds < 3600 ? `${Math.max(1, Math.round(seconds / 60))} دقيقة` : `${Math.floor(seconds / 3600)} س ${Math.round(seconds % 3600 / 60)} د`; }
