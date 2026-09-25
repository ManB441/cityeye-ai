# CityEye Google Maps integration

Status: implemented locally; actual Google basemap validation awaits an API key.
No Google account, billing plan, camera coordinates or road geometry was created.

## Activate the development map

1. In your Google Cloud project, enable Maps JavaScript API and configure the
   billing account yourself. Restrict the browser key to **Maps JavaScript API**
   and your development website referrers (for example `http://localhost:5173/*`
   and `http://127.0.0.1:5173/*`; include a different port only when you use it).
   Configure quotas and billing alerts in Google Cloud. Alerts are not hard caps.
2. Copy `frontend/.env.example` to `frontend/.env.local` and set
   `VITE_GOOGLE_MAPS_API_KEY=your_browser_key`. Do not paste the key into chat or Git.
   Browser keys are visible in requests/bundles; website/API restrictions protect
   their usage. Never put a server credential in a VITE variable.
3. Restart the frontend dev server, then open `/citizen-map`. Without a key,
   setup instructions appear and no Google Maps script is requested.
4. For Docker, export the same variable in the shell used to build the frontend;
   Compose passes it as a build argument. Vite consumes it at build time, so merely
   restarting an old frontend image does not add the key. Production deployment
   is a separate step; this task did not recreate the existing containers.

The SDK is loaded once per page lifetime. Updating CityEye layers does not recreate
the base map every polling interval. Network/authentication failures show a visible
error. Actual Google authorization, billing restrictions and basemap rendering
cannot be certified without the user's key.

The frontend CSP allows Google Maps resource domains and the SDK's `unsafe-eval`
requirement, but not inline scripts. Referrer policy is `strict-origin-when-cross-origin`
so Google can validate website restrictions without receiving URL paths. Backend
API CSP remains unchanged. Verify CSP behavior with the real authorized key before
public deployment; this was not bypassed by disabling CSP.

References: https://developers.google.com/maps/documentation/javascript/load-maps-js-api
and https://developers.google.com/maps/documentation/javascript/content-security-policy

## Configure actual geography separately from video ROIs

Copy `backend/map-config.example.json` to a local file such as `secrets/map.json`.
The example is intentionally empty. Set `CITYEYE_MAP_CONFIG` to its absolute path
for a local backend, or `/run/secrets/map.json` for the existing Compose secret mount.
Configuration is read on map requests; an invalid file produces HTTP 503 instead
of guessed geometry. Do not commit confidential camera geography.

Each entry in `cameras` accepts:

- `camera_id`: existing identity such as camera-3; duplicate IDs are rejected.
- `label`: descriptive camera/coverage name.
- `position`: `{ "lat": <confirmed latitude>, "lng": <confirmed longitude> }`.
- `location_confirmed`: true only after verifying the position with the operator.
- `road`: ordered geographic positions defining ONLY the monitored road segment.
  At least two distinct points are required if a road is supplied. These are not
  the 944×1080 image ROI coordinates; no automatic image-to-GPS conversion exists.
- `traffic_calibrated`: true only when this segment corresponds to the camera's
  calibrated congestion region. Otherwise its road condition remains UNKNOWN.
- `public`: false by default. Set true only for coverage explicitly approved for
  the citizen view. Camera infrastructure itself remains hidden from citizens.

No existing camera/event latitude fallback is used. In particular, historical
0,0 placeholders and the Maydan recording are not assigned to invented map locations.
An empty map initially opens at world view; its center is not a camera marker.

## Meaning of layers

Roads: green NORMAL, amber MODERATE, red HEAVY_CONGESTION, gray UNKNOWN/stale.
Use the existing AI status only when a fresh, matching-generation observation and
confirmed traffic mapping exist. Browser expiry uses the server freshness budget,
subtracting request transit time conservatively. A stalled poll cannot retain a
green road indefinitely. API failure removes the observations and shows an error.

Cameras: staff-only points; show freshness and sampled vehicle count when available.
The count is not throughput. Image/video previews and credentials are not exposed
through the map endpoint.

AI incidents: the existing STOPPED_VEHICLE, WRONG_WAY, CONGESTION and ROAD_BLOCKAGE
types. Orange means proposed, purple means verified; dismissed events are omitted.
Pins indicate the configured camera area, NOT exact vehicle GPS. Up to 100 recent
incidents per camera, within 24 hours, are shown with timestamps; they are not
claimed to remain active. Citizens see only verified incidents on public coverage.
No collision/accident detector or invented directional arrow was added.

Citizen reports: blue pending, darker blue community-confirmed, on user-submitted
coordinates. Up to 200 reports within 24 hours are shown. Community confirmation is
not AI/municipal verification. Voter/account IDs are omitted from the map response.
Automatic geographic/temporal corroboration remains unimplemented.

The layer controls and parallel text list work without the SDK. Selecting a map
point or list row shows type/status/time/location precision. Both surfaces use the
same feature collection. Google TrafficLayer is deliberately not enabled: road
colors here represent CityEye observations, not Google's traffic estimates.

## Validation

276 backend tests and 90 frontend tests passed; TypeScript and production build
passed. New tests cover missing/unconfirmed geography, stale data, congestion
calibration gating, citizen redaction, authentication, invalid configuration,
report identity redaction, SDK reuse, layer selection and API failure. A local
isolated browser preview verified the no-key/setup and empty-geography states.
SDK drawing interactions were tested with a mock; actual Google tiles, credentials
and production CSP remain awaiting key-based validation. No production DB writes,
real camera relocation, ROI/model/threshold changes or container deployment occurred.
