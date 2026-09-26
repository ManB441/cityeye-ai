import { expect, it } from "vitest";
import { humanDistance, nearestRoutePoint, remainingDistance, routeRelevantFeatures } from "./navigation";
import type { RouteOption } from "./google";

const route: RouteOption = { path: [{ lat: 31.95, lng: 35.9 }, { lat: 31.951, lng: 35.901 }, { lat: 31.952, lng: 35.902 }], distanceMeters: 300, durationSeconds: 60, steps: [], summary: "Test" };

it("finds route progress and calculates only the remaining actual path", () => {
  expect(nearestRoutePoint(route.path, { lat: 31.9511, lng: 35.9011 }).index).toBe(1);
  expect(remainingDistance(route, 1)).toBeGreaterThan(100);
  expect(humanDistance(1250)).toBe("1.3 كم");
});

it("marks only existing CityEye observations near the route", () => {
  const features: any[] = [
    { id: "near", geometry: { type: "Point", coordinates: [35.901, 31.951] }, properties: {} },
    { id: "far", geometry: { type: "Point", coordinates: [36, 32] }, properties: {} }
  ];
  expect(routeRelevantFeatures(features, route.path).map(feature => feature.id)).toEqual(["near"]);
});
