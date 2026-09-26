import { useEffect, useRef, useState } from "react";
import { COLORS, type MapFeature } from "./model";
import { loadGoogleMaps, type GoogleMap, type Position, type RouteOption } from "./google";

export function GoogleTrafficMap({ features, onSelect, origin, destination, onPick, routes = [], selectedRoute = 0, routeProgress = 0, currentPosition, apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "" }:
  { features: MapFeature[]; onSelect: (id: string) => void; apiKey?: string; origin?: Position; destination?: Position; onPick?: (point: Position) => void; routes?: RouteOption[]; selectedRoute?: number; routeProgress?: number; currentPosition?: Position }) {
  const container = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<GoogleMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const fitted = useRef(false);
  const routeShapes = useRef<Array<{ setMap(map: GoogleMap | null): void }>>([]);
  const journeyMarkers = useRef<Array<{ setMap(map: GoogleMap | null): void }>>([]);
  const pick = useRef(onPick); pick.current = onPick;
  const initialOrigin = useRef(origin);
  const select = useRef(onSelect); select.current = onSelect;
  useEffect(() => {
    if (!apiKey) return;
    let active = true;
    let clickListener: { remove(): void } | undefined;
    let listener: { remove(): void } | undefined;
    const authFailed = () => { if (active) setError("Google Maps authorization failed. Check your key and allowed websites."); };
    window.addEventListener("cityeye-map-auth-error", authFailed);
    setError(null);
    void loadGoogleMaps(apiKey).then(sdk => {
      if (!active || !container.current) return;
      const instance = new sdk.Map(container.current, { center: initialOrigin.current ?? { lat: 0, lng: 0 }, zoom: initialOrigin.current ? 15 : 2,
        maxZoom: 19, mapTypeControl: false, streetViewControl: false, fullscreenControl: true });
      instance.data.setStyle(feature => {
        const status = String(feature.getProperty("status"));
        const kind = feature.getProperty("kind");
        const color = COLORS[status as keyof typeof COLORS] ?? COLORS.UNKNOWN;
        return { strokeColor: color, strokeWeight: 7, strokeOpacity: .9,
          icon: { path: sdk.SymbolPath.CIRCLE, scale: kind === "incident" ? 11 : kind === "camera" ? 7 : 8,
            fillColor: color, fillOpacity: status === "PROPOSED" ? .25 : .95, strokeColor: color, strokeWeight: 3 },
          title: `${String(feature.getProperty("label"))} · ${status}` };
      });
      if (pick.current) clickListener = instance.addListener("click", event => { if (event.latLng) pick.current?.({ lat: event.latLng.lat(), lng: event.latLng.lng() }); });
      listener = instance.data.addListener("click", event => select.current(String(event.feature.getProperty("id"))));
      fitted.current = false; setMap(instance);
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Map unavailable"); });
    return () => { active = false; listener?.remove(); clickListener?.remove(); window.removeEventListener("cityeye-map-auth-error", authFailed); };
  }, [apiKey, retry]);
  useEffect(() => {
    if (!map) return;
    map.data.forEach(feature => map.data.remove(feature));
    map.data.addGeoJson({ type: "FeatureCollection", features });
    const journey = [origin, destination].flatMap((point, i) => point ? [{ type: "Feature", id: `journey-${i}`, geometry: { type: "Point", coordinates: [point.lng, point.lat] }, properties: { id: `journey-${i}`, kind: "report", label: i ? "Destination" : "Your starting point", status: i ? "VERIFIED" : "PENDING" } }] : []);
    if (journey.length) map.data.addGeoJson({ type: "FeatureCollection", features: journey as MapFeature[] });
    if (!origin && !fitted.current && features.length && window.google) {
      const bounds = new window.google.maps.LatLngBounds();
      features.forEach(feature => {
        const points = feature.geometry.type === "Point" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
        points.forEach(([lng, lat]) => bounds.extend({ lat, lng }));
      });
      map.fitBounds(bounds); fitted.current = true;
    }
  }, [map, features, origin, destination]);
  useEffect(() => { if (map && origin) { map.setCenter(origin); map.setZoom(15); } }, [map, origin]);
  useEffect(() => { if (map && currentPosition) { map.setCenter(currentPosition); map.setZoom(16); } }, [map, currentPosition]);
  useEffect(() => {
    if (!map || !window.google?.maps) return;
    routeShapes.current.forEach(shape => shape.setMap(null));
    journeyMarkers.current.forEach(marker => marker.setMap(null));
    routeShapes.current = [];
    journeyMarkers.current = [];
    const sdk = window.google.maps;
    routes.forEach((route, index) => {
      if (index === selectedRoute) {
        const complete = route.path.slice(0, Math.max(1, routeProgress + 1));
        const remaining = route.path.slice(Math.max(0, routeProgress));
        if (complete.length > 1) routeShapes.current.push(new sdk.Polyline({ path: complete, map, strokeColor: "#647987", strokeOpacity: .8, strokeWeight: 6 }));
        if (remaining.length > 1) routeShapes.current.push(new sdk.Polyline({ path: remaining, map, strokeColor: "#18c6c4", strokeOpacity: .95, strokeWeight: 7 }));
      } else routeShapes.current.push(new sdk.Polyline({ path: route.path, map, strokeColor: "#71818d", strokeOpacity: .6, strokeWeight: 4 }));
    });
    if (currentPosition) journeyMarkers.current.push(new sdk.Marker({ position: currentPosition, map, title: "Your current location", icon: { path: sdk.SymbolPath.CIRCLE, scale: 8, fillColor: "#18c6c4", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2 } }));
    if (destination) journeyMarkers.current.push(new sdk.Marker({ position: destination, map, title: "Destination" }));
    return () => { routeShapes.current.forEach(shape => shape.setMap(null)); journeyMarkers.current.forEach(marker => marker.setMap(null)); };
  }, [map, routes, selectedRoute, routeProgress, currentPosition, destination]);
  return <div className="traffic-map-shell">
    <div ref={container} className="google-traffic-map" aria-label="CityEye geographic map" />
    {!apiKey ? <div className="map-setup"><strong>Google Maps setup required</strong><p>Add a restricted Maps JavaScript API key to your local frontend environment to display the map. No Google requests are made before configuration.</p></div>
      : error ? <div className="map-setup" role="alert"><p>{error}</p><button onClick={() => setRetry(value => value + 1)}>Retry map</button></div>
      : !map ? <div className="map-setup" role="status">Loading Google Maps…</div> : null}
  </div>;
}
