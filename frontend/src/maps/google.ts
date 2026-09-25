// Narrow SDK surface used by this integration; no key or response is logged.
import type { MapFeature } from "./model";
export type DataFeature = { getProperty(name: string): unknown };
export type GoogleMap = {
  data: { addGeoJson(data: { type: string; features: MapFeature[] }): void;
    forEach(callback: (feature: DataFeature) => void): void; remove(feature: DataFeature): void;
    setStyle(callback: (feature: DataFeature) => object): void;
    addListener(name: string, callback: (event: { feature: DataFeature }) => void): { remove(): void } };
  fitBounds(bounds: object): void;
};
export type GoogleSDK = {
  Map: new (element: HTMLElement, options: object) => GoogleMap;
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
    const query = new URLSearchParams({ key, loading: "async", callback: "cityeyeMapReady", v: "quarterly" });
    script.src = `https://maps.googleapis.com/maps/api/js?${query}`;
    script.async = true; script.onerror = fail;
    document.head.append(script);
  });
  return pending;
}
