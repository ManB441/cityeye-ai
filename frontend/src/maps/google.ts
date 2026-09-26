// Narrow SDK surface used by this integration; no key or response is logged.
import type { MapFeature } from "./model";
export type DataFeature = { getProperty(name: string): unknown };
export type Position = { lat: number; lng: number };
export type RouteStep = { instruction: string; end: Position; distanceMeters: number; durationSeconds: number };
export type RouteOption = { path: Position[]; distanceMeters: number; durationSeconds: number; steps: RouteStep[]; summary: string };
export type GoogleMap = {
  setCenter(point: Position): void;
  setZoom(zoom: number): void;
  addListener(name: string, callback: (event: { latLng?: { lat(): number; lng(): number } }) => void): { remove(): void };
  data: { addGeoJson(data: { type: string; features: MapFeature[] }): void;
    forEach(callback: (feature: DataFeature) => void): void; remove(feature: DataFeature): void;
    setStyle(callback: (feature: DataFeature) => object): void;
    addListener(name: string, callback: (event: { feature: DataFeature }) => void): { remove(): void } };
  fitBounds(bounds: object): void;
};
export type GoogleSDK = {
  Map: new (element: HTMLElement, options: object) => GoogleMap;
  Polyline: new (options: { path: Position[]; map: GoogleMap; strokeColor: string; strokeOpacity: number; strokeWeight: number }) => { setMap(map: GoogleMap | null): void };
  Marker: new (options: { position: Position; map: GoogleMap; title: string; icon?: object }) => { setMap(map: GoogleMap | null): void };
  LatLngBounds: new () => { extend(point: { lat: number; lng: number }): void };
  SymbolPath: { CIRCLE: number };
};
declare global {
  interface Window { google?: { maps: GoogleSDK }; cityeyeMapReady?: () => void; gm_authFailure?: () => void }
}
let pending: Promise<GoogleSDK> | null = null;
export function loadGoogleMaps(key: string): Promise<GoogleSDK> {
  if (!key.trim()) return Promise.reject(new Error("Google Maps key is not configured"));
  if (pending) return pending;
  if (window.google?.maps.Map) return Promise.resolve(window.google.maps);
  pending = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    let finished = false;
    const fail = () => {
      window.dispatchEvent(new Event("cityeye-map-auth-error"));
      if (finished) return;
      finished = true; clearTimeout(timer); pending = null; script.remove();
      reject(new Error("Google Maps could not load. Check the key, billing, allowed websites and network."));
    };
    const timer = window.setTimeout(fail, 20000);
    window.cityeyeMapReady = () => {
      if (finished) return;
      if (!window.google?.maps.Map) { fail(); return; }
      finished = true; clearTimeout(timer); resolve(window.google.maps);
    };
    window.gm_authFailure = fail;
    const query = new URLSearchParams({ key, loading: "async", callback: "cityeyeMapReady", v: "quarterly", libraries: "geometry,places" });
    script.src = `https://maps.googleapis.com/maps/api/js?${query}`;
    script.async = true; script.onerror = fail;
    document.head.append(script);
  });
  return pending;
}

type LegacyDirectionsResult = { routes?: Array<{ overview_path?: Array<{ lat(): number; lng(): number }>; summary?: string; legs?: Array<{ distance?: { value?: number }; duration?: { value?: number }; steps?: Array<{ instructions?: string; end_location?: { lat(): number; lng(): number }; distance?: { value?: number }; duration?: { value?: number } }> }> }> };

function position(point: { lat(): number; lng(): number }): Position { return { lat: point.lat(), lng: point.lng() }; }
function plainText(value: string | undefined): string { return (value ?? "Continue").replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim(); }

/** Uses Google's actual routing response; it never joins coordinates with a synthetic line. */
export async function calculateGoogleRoutes(origin: Position, destination: Position): Promise<RouteOption[]> {
  const maps = window.google?.maps as unknown as { importLibrary?: (name: string) => Promise<{ DirectionsService?: new () => { route(request: object, callback: (result: LegacyDirectionsResult | null, status: string) => void): void } }> } | undefined;
  const library = await maps?.importLibrary?.("routes");
  const DirectionsService = library?.DirectionsService;
  if (!DirectionsService) throw new Error("Routing is not available for the configured Google Maps project.");
  const result = await new Promise<LegacyDirectionsResult>((resolve, reject) => new DirectionsService().route(
    { origin, destination, travelMode: "DRIVING", provideRouteAlternatives: true, language: "ar" },
    (response, status) => status === "OK" && response ? resolve(response) : reject(new Error(status))
  ));
  const routes = (result.routes ?? []).map(route => {
    const leg = route.legs?.[0];
    const path = (route.overview_path ?? []).map(position);
    return {
      path,
      distanceMeters: leg?.distance?.value ?? 0,
      durationSeconds: leg?.duration?.value ?? 0,
      steps: (leg?.steps ?? []).flatMap(step => step.end_location ? [{ instruction: plainText(step.instructions), end: position(step.end_location), distanceMeters: step.distance?.value ?? 0, durationSeconds: step.duration?.value ?? 0 }] : []),
      summary: route.summary ?? ""
    };
  }).filter(route => route.path.length >= 2);
  if (!routes.length) throw new Error("ZERO_RESULTS");
  return routes;
}

export async function geocodeDestination(query: string, bias?: Position): Promise<Position> {
  const maps = window.google?.maps as unknown as { Geocoder?: new () => { geocode(request: object, callback: (results: unknown, status: string) => void): void }; places?: { PlacesService?: new (container: HTMLElement) => { findPlaceFromQuery(request: object, callback: (results: unknown, status: string) => void): void } } } | undefined;
  const Geocoder = maps?.Geocoder;
  const fromResult = (results: unknown) => (results as Array<{ geometry?: { location?: { lat(): number; lng(): number } } }> | null)?.[0]?.geometry?.location;
  let geocoderStatus = "SEARCH_UNAVAILABLE";
  if (Geocoder) {
    const result = await new Promise<{ location?: { lat(): number; lng(): number }; status: string }>(resolve => new Geocoder().geocode({ address: query, location: bias }, (results, status) => resolve({ location: fromResult(results), status })));
    if (result.status === "OK" && result.location) return position(result.location);
    geocoderStatus = result.status;
  }
  const PlacesService = maps?.places?.PlacesService;
  if (!PlacesService) throw new Error(geocoderStatus === "ZERO_RESULTS" ? "ZERO_RESULTS" : "SEARCH_UNAVAILABLE");
  return new Promise((resolve, reject) => new PlacesService(document.createElement("div")).findPlaceFromQuery({ query, fields: ["geometry", "name"], locationBias: bias }, (results, status) => {
    const location = fromResult(results);
    if (status === "OK" && location) resolve(position(location)); else reject(new Error(status === "ZERO_RESULTS" && geocoderStatus === "ZERO_RESULTS" ? "ZERO_RESULTS" : "SEARCH_UNAVAILABLE"));
  }));
}
