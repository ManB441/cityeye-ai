import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GoogleTrafficMap } from "./GoogleTrafficMap";
import { calculateGoogleRoutes, geocodeDestination, loadGoogleMaps, type Position, type RouteOption } from "./google";
import { humanDistance, humanDuration, metersBetween, nearestRoutePoint, nextRouteStep, remainingDistance, routeRelevantFeatures } from "./navigation";
import type { MapFeature } from "./model";

type RouteState = "idle" | "routing" | "ready" | "failed";
const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "";

function routeErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  if (code === "ZERO_RESULTS") return "لا يوجد مسار قيادة متاح لهذه الوجهة.";
  if (code === "REQUEST_DENIED" || code.includes("Routing is not available")) return "خدمة المسارات غير مفعّلة لمفتاح Google Maps الحالي.";
  return "تعذر حساب المسار الآن. حاول مرة أخرى بعد قليل.";
}

function destinationErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  if (code === "ZERO_RESULTS") return "لم نجد هذه الوجهة. جرّب اسمًا أو عنوانًا أوضح، أو حددها على الخريطة.";
  if (["REQUEST_DENIED", "SEARCH_UNAVAILABLE", "OVER_QUERY_LIMIT"].includes(code)) return "البحث عن الأماكن غير مفعّل لمفتاح الخريطة الحالي. يمكنك تحديد وجهتك بالنقر على الخريطة.";
  return "تعذر البحث عن المكان الآن. حاول مرة أخرى بعد قليل أو حدد وجهتك على الخريطة.";
}

function speak(text: string) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ar";
  window.speechSynthesis.speak(utterance);
}

export function JourneyMap({ features, onSelect }: { features: MapFeature[]; onSelect: (id: string) => void }) {
  const [origin, setOrigin] = useState<Position>();
  const [destination, setDestination] = useState<Position>();
  const [destinationQuery, setDestinationQuery] = useState("");
  const [locationPending, setLocationPending] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteOption[]>([]);
  const [selectedRoute, setSelectedRoute] = useState(0);
  const [routeState, setRouteState] = useState<RouteState>("idle");
  const [routeError, setRouteError] = useState<string | null>(null);
  const [navigationActive, setNavigationActive] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [currentPosition, setCurrentPosition] = useState<Position>();
  const [routeProgress, setRouteProgress] = useState(0);
  const [navigationNotice, setNavigationNotice] = useState<string | null>(null);
  const [arrived, setArrived] = useState(false);
  const request = useRef(0);
  const offRouteSamples = useRef(0);
  const lastVoice = useRef("");
  const selected = routes[selectedRoute];

  useEffect(() => () => { request.current++; window.speechSynthesis?.cancel(); }, []);

  const calculateRoute = useCallback(async (start: Position, end: Position, preserveNavigation = false) => {
    setRouteState("routing"); setRouteError(null);
    if (preserveNavigation) setNavigationNotice("جارٍ إعادة حساب المسار…");
    try {
      await loadGoogleMaps(API_KEY);
      const nextRoutes = await calculateGoogleRoutes(start, end);
      setRoutes(nextRoutes); setSelectedRoute(0); setRouteProgress(0); setCurrentPosition(start);
      setRouteState("ready"); setNavigationNotice(null); setArrived(false);
      if (!preserveNavigation) setNavigationActive(false);
    } catch (error) { setRoutes([]); setRouteState("failed"); setRouteError(routeErrorMessage(error)); setNavigationNotice(preserveNavigation ? "تعذر تحديث المسار الآن. حاول متابعة الطريق بأمان ثم أعد المحاولة." : null); }
  }, []);

  function locate() {
    const id = ++request.current;
    if (!navigator.geolocation) { setLocationError("تعذر الوصول إلى موقع جهازك. استخدم متصفحًا يدعم خدمات الموقع ثم حاول مرة أخرى."); return; }
    setLocationPending(true); setLocationError(null);
    navigator.geolocation.getCurrentPosition(position => {
      if (id !== request.current) return;
      const point = { lat: position.coords.latitude, lng: position.coords.longitude };
      setOrigin(point); setCurrentPosition(point); setDestination(undefined); setRoutes([]); setNavigationActive(false); setArrived(false); setLocationPending(false);
    }, error => {
      if (id !== request.current) return;
      setLocationPending(false);
      setLocationError(error.code === 1 ? "نحتاج إلى إذن الموقع لعرض معلومات الخريطة القريبة منك." : "تعذر تحديد موقعك الآن. تأكد من تشغيل خدمات الموقع ثم حاول مرة أخرى.");
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }

  // A previously granted permission is safe to use on entry and does not show a
  // browser prompt. New or denied permissions still require an explicit action.
  useEffect(() => {
    let active = true;
    if (!navigator.permissions?.query) return () => { active = false; };
    void navigator.permissions.query({ name: "geolocation" }).then(status => {
      if (active && status.state === "granted") locate();
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  function chooseDestination(point: Position) {
    if (!origin) return;
    setDestination(point); void calculateRoute(currentPosition ?? origin, point);
  }

  async function searchDestination(event: React.FormEvent) {
    event.preventDefault();
    if (!origin || !destinationQuery.trim()) return;
    setRouteState("routing"); setRouteError(null);
    try {
      await loadGoogleMaps(API_KEY);
      chooseDestination(await geocodeDestination(destinationQuery.trim(), currentPosition ?? origin));
    } catch (error) { setRouteState("failed"); setRouteError(destinationErrorMessage(error)); }
  }

  useEffect(() => {
    if (!navigationActive || !destination || !selected || !navigator.geolocation) return;
    const watchId = navigator.geolocation.watchPosition(position => {
      const point = { lat: position.coords.latitude, lng: position.coords.longitude };
      setCurrentPosition(point);
      if (metersBetween(point, destination) <= 35) { setNavigationActive(false); setArrived(true); setNavigationNotice(null); return; }
      const closest = nearestRoutePoint(selected.path, point);
      setRouteProgress(closest.index);
      if (closest.distanceMeters > 70) offRouteSamples.current += 1; else offRouteSamples.current = 0;
      if (offRouteSamples.current >= 2) { offRouteSamples.current = 0; void calculateRoute(point, destination, true); }
    }, () => setNavigationNotice("تعذر تحديث موقعك مؤقتًا. سنحاول مجددًا."), { enableHighAccuracy: true, maximumAge: 3000, timeout: 10000 });
    return () => navigator.geolocation.clearWatch(watchId);
  }, [navigationActive, destination, selected, calculateRoute]);

  const nextStep = selected && currentPosition ? nextRouteStep(selected, currentPosition) : undefined;
  useEffect(() => {
    if (!navigationActive || !voiceEnabled || !nextStep || !currentPosition) return;
    const distance = metersBetween(currentPosition, nextStep.end);
    const threshold = distance <= 60 ? "near" : distance <= 200 ? "ahead" : "";
    const key = `${nextStep.instruction}:${threshold}`;
    if (threshold && key !== lastVoice.current) { lastVoice.current = key; speak(`${nextStep.instruction} بعد ${humanDistance(distance)}`); }
  }, [navigationActive, voiceEnabled, nextStep, currentPosition]);

  const remaining = selected ? remainingDistance(selected, routeProgress) : 0;
  const cityEyeAlerts = useMemo(() => selected ? routeRelevantFeatures(features, selected.path) : [], [features, selected]);
  return <div className="journey-map">
    <GoogleTrafficMap features={features} onSelect={onSelect} origin={origin} destination={destination} onPick={chooseDestination} routes={routes} selectedRoute={selectedRoute} routeProgress={routeProgress} currentPosition={navigationActive ? currentPosition : undefined} />
    {!origin ? <section className="location-prompt" dir="rtl" aria-label="تحديد الموقع">
      <h2>حدد موقعك لعرض المعلومات القريبة منك</h2><p>نحتاج إلى موقعك لعرض حالة الطرق والحوادث والكاميرات القريبة منك.</p>
      {locationError && <p className="location-prompt-error" role="alert">{locationError}</p>}
      <button disabled={locationPending} onClick={locate}>{locationPending ? "جارٍ تحديد موقعك…" : locationError ? "حاول مرة أخرى" : "تحديد موقعي"}</button>
    </section> : <>
      <section className="navigation-panel" dir="rtl" aria-label="التنقل">
        <span className="map-mode">{arrived ? "تم الوصول" : navigationActive ? "تنقل نشط" : selected ? "معاينة المسار" : "استكشف منطقتك"}</span>
        {navigationActive && selected ? <div className="next-maneuver"><strong>{nextStep?.instruction ?? "تابع إلى وجهتك"}</strong><span>{nextStep && currentPosition ? `بعد ${humanDistance(metersBetween(currentPosition, nextStep.end))}` : ""}</span></div> : null}
        <form className="destination-search" onSubmit={searchDestination}>
          <label htmlFor="destination-search">إلى أين تريد الذهاب؟</label>
          <div><input id="destination-search" value={destinationQuery} onChange={event => setDestinationQuery(event.target.value)} placeholder="ابحث عن مكان أو عنوان" autoComplete="off" /><button disabled={routeState === "routing"}>{routeState === "routing" ? "جارٍ البحث…" : "بحث"}</button><button className="location-refresh" type="button" onClick={locate} disabled={locationPending}>{locationPending ? "جارٍ التحديث…" : "موقعي"}</button></div>
        </form>
        <p className="destination-hint">أو اضغط على الخريطة لتحديد وجهتك.</p>
        {routeError && <p className="navigation-error" role="alert">{routeError}</p>}
        {navigationNotice && <p className="navigation-notice" role="status">{navigationNotice}</p>}
        {arrived && <div className="arrival-card"><strong>✓ وصلت إلى وجهتك</strong><span>{destinationQuery.trim() || "الوجهة المحددة"}</span><button type="button" onClick={() => { setArrived(false); setDestination(undefined); setRoutes([]); setRouteState("idle"); }}>استكشف المنطقة</button></div>}
        {selected && !arrived && <div className="route-summary"><strong>{humanDuration(navigationActive ? Math.round(selected.durationSeconds * (remaining / Math.max(1, selected.distanceMeters))) : selected.durationSeconds)}</strong><span>{humanDistance(navigationActive ? remaining : selected.distanceMeters)}</span><small>{selected.summary || "مسار قيادة"}</small></div>}
        {routes.length > 1 && <div className="route-options" aria-label="مسارات بديلة">{routes.map((route, index) => <button className={index === selectedRoute ? "selected" : ""} key={`${route.summary}-${index}`} onClick={() => { setSelectedRoute(index); setRouteProgress(0); }}><strong>{humanDuration(route.durationSeconds)}</strong><span>{humanDistance(route.distanceMeters)}</span></button>)}</div>}
        {selected && !arrived && <div className="navigation-actions"><button onClick={() => { setNavigationActive(value => !value); lastVoice.current = ""; }}>{navigationActive ? "إيقاف التنقل" : "بدء التنقل"}</button><label><input type="checkbox" checked={voiceEnabled} onChange={event => setVoiceEnabled(event.target.checked)} />إرشاد صوتي</label></div>}
      </section>
      {selected && <section className="route-alerts" dir="rtl" aria-label="تنبيهات CityEye على المسار"><h2>تنبيهات CityEye القريبة من المسار</h2>{cityEyeAlerts.length ? cityEyeAlerts.map(feature => <button key={feature.id} onClick={() => onSelect(feature.id)}><strong>{feature.properties.label}</strong><span>{feature.properties.status} · قرب تقريبي من المسار</span></button>) : <p>لا توجد ملاحظات CityEye متموضعة قرب هذا المسار حاليًا.</p>}</section>}
    </>}
  </div>;
}
