# CityEye secure access

## Enable access control

The existing SQLite users, PBKDF2-SHA256 password hashes, opaque sessions, and
ADMIN / EMPLOYEE / CITIZEN roles use one authentication system. On upgrade, existing
OPERATOR and REVIEWER accounts become EMPLOYEE. Account IDs, password hashes,
activation states and existing sessions are preserved; permissions resolve from
the current database role on every request.

Set `CITYEYE_AUTH_REQUIRED=true` for a secured local/demo environment. Production
requires it and refuses to start with authentication disabled. Existing development
and Compose demo defaults still allow unauthenticated demo access; they are not a
secured deployment. Following initial validation, the local backend/frontend were
redeployed with authentication enabled in the ignored `.env`, an administrator
provisioned from protected local secret files, and the existing database preserved.

For a database with no users, configure:

- `CITYEYE_BOOTSTRAP_ADMIN_USERNAME`: the administrator's municipal email or username.
- `CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE`: a protected secret file containing a
  password of at least 12 characters. With Compose, mount it as
  `/run/secrets/admin_password` using `CITYEYE_SECRETS_DIR`.
- `CITYEYE_INGEST_TOKEN_FILE`: a separate machine secret, mounted as
  `/run/secrets/ingest_token` with Compose.

Use the deployment secret manager or a local file readable only by the service
owner. Do not put passwords in source, frontend configuration, URLs, or shell
arguments. Bootstrap only runs when the user table is empty; it does not overwrite
existing accounts. Once signed in as ADMIN, use **User access** (`/users`) to create
EMPLOYEE and CITIZEN accounts, change roles, and enable/disable accounts. There
are no hardcoded demo accounts in the frontend. Email addresses use the existing
case-insensitive username field; separate profile/display-name management is not
implemented.

Production also requires HTTPS, explicit trusted hosts, and exact HTTPS origins
in `CITYEYE_CORS_ORIGINS`. Browser requests use the same origin via Vite/nginx.
Origin validation includes the port. nginx preserves the incoming Host header.

## Sessions and authorization

Login returns current-user metadata and expiry, and sets `cityeye_session`:
HttpOnly, SameSite=Strict, Path=/, Secure in production. The default absolute
lifetime is eight hours, configurable from five minutes to 24 hours. Every login
creates a new random 256-bit token; only its SHA-256 digest is persisted. Passwords
retain salted PBKDF2-SHA256 with 310,000 iterations. Unknown/inactive usernames
perform equivalent password-verification work and receive the same invalid-login
message. Tokens are not returned in login JSON or stored in browser storage.

Refresh checks `/api/auth/session` before mounting protected content. Session
errors fail closed. The frontend rechecks on window focus and every 30 seconds;
protected API 401 responses immediately clear the authenticated UI. Role changes
are resolved from the database on every backend request. Logout revokes the
server-side token and deletes the cookie; a failed logout reports an error and
does not falsely claim success. Disabling an account revokes all its sessions.
The final active administrator cannot be demoted or disabled; access updates
serialize their guard and write within one SQLite transaction.

- ADMIN: every product function, incident review, audit and user administration.
- EMPLOYEE: monitoring, cameras, incidents, analytics, map, Verify/Dismiss and audit;
  no account creation, role changes, or enabling/disabling other accounts.
- CITIZEN: Citizen Map and its report APIs only; no operational dashboards,
  camera streams, media, evidence, incidents, analytics, audit or user administration.

Citizens land on `/citizen-map` after login. Direct links to protected operational
routes and aliases redirect to that map without mounting those pages or fetching
operational data. The API independently denies operational reads and writes with
403, including direct media/evidence URLs. Employees visiting `/users` receive
Access restricted. Only admins see User access and can select the three roles.
Account access is managed here; no separate billing/subscription service exists.

All `/api/*`, `/media/*`, and `/evidence/*` product reads require authentication.
Public exceptions are health checks, login/session discovery, token-protected
AI ingestion, and the existing citizen-report POST. API documentation is disabled
in production. All ingested, recorded-scenario, legacy live-camera, and selected
live-camera Verify/Dismiss endpoints require ADMIN or EMPLOYEE. User create/list/
update APIs require ADMIN; audit reads also allow EMPLOYEE. Missing sessions return 401; insufficient
roles return 403. Browser writes reject untrusted Origin headers. Product responses
use no-store, and rejected requests retain security headers and request IDs.

Login success/failure, logout, user changes and incident decisions are audited.
AI ingestion retains its independent `X-CityEye-Ingest-Token` mechanism.

## Recovery and implementation scope

Recovered branch: `codex/live-camera-operational-analytics`. Initial state:
eight modified tracked files and one untracked LoginPage; 212 insertions and 87
deletions in tracked files. No reset, checkout, commit or push was performed.

Already implemented: libVLC capture with independent preview publication, sampled
YOLO/ByteTrack inference, movement states, stopped-vehicle prior-motion/ROI/duration/
deduplication/rearm rules, proposed incidents with human review, recorded scenarios,
and Analytics V1 persistence/API/UI/tests. The existing running database contained
144 real traffic samples when inspected. Analytics functionality was left intact;
its API client now participates in session-expiry handling. Prediction and
multi-camera analytics remain unavailable. Road blockage is not proven operational
for Camera 3; camera-specific calibration is still required. Citizen Map remains
a placeholder despite older README language.

This change finishes the partial cookie-login work: fail-closed route bootstrap,
error/loading/duplicate-submit handling, session restoration and expiry handling,
logout correctness, live incident RBAC, admin API integration, current-user menu,
and a responsive navy/teal login screen. Motion uses sparse ambient node pulses,
a short card entrance and button transitions, disabled under reduced-motion.
The password toggle has a separate accessible label; controls have visible focus.
No AI model, tracking, camera performance or event-rule code was changed.

## Validation on 2026-09-17

Baseline: 173 backend tests, 185 AI tests, 25 frontend tests, and frontend build
passed. The root `.venv` lacks pytest; the actual backend/AI virtual environments
were used.

Final validation covers:

- 211 backend tests, including cookie flags/expiry, hashed session storage, logout
  revocation, account disabling, final-admin protection, Origin checks, private
  data/media endpoints, and all four incident-source permission boundaries.
- 35 frontend tests covering direct-route redirects, unavailable auth service,
  duplicate submission, restricted roles and successful/failed logout.
- 185 AI tests; real VIDEO_FILE execution of 30 frames yielded 291 track records,
  annotated MP4, and an honest empty event list for that short segment.
- Production frontend build, Python compilation, both Compose configurations,
  and `git diff --check`.
- Docker smoke test: 37 checks on a separate stack: recorded scenarios, MP4 ranges, evidence,
  incident decisions and persistence, and authentication through nginx.
- Real Chromium browser with generated temporary accounts and an isolated database:
  direct protected URLs, invalid credentials, password visibility, Enter submission,
  ADMIN identity/refresh/account creation, OPERATOR 403s, REVIEWER decisions,
  Access restricted, logout cookie deletion and revoked-token rejection. Supplemental
  browser checks verified keyboard focus, a REVIEWER Verify action through the UI,
  and safe errors/no protected content during simulated login/session outages.
- Visual inspection at 1440×900, 1280×800, 390×844 and 320×640; no horizontal
  overflow. Reduced-motion computed styles disable login animations.
- Camera 3 LIVE frames changed during browser observation; authenticated AI VIEW
  rendered processed frames. Real collected analytics loaded. Cameras 5/7 remained
  offline. One recovery sample measured ~12 capture / 10.8 preview / 3.8 AI FPS;
  this is a point observation, not a performance guarantee. The current camera
  image was visibly blurred; authentication work does not improve camera quality.

## Remaining scope

No built-in login rate limiter existed and none was added; configure edge-level
brute-force protection before external exposure. Password reset/change, MFA,
passkeys/WebAuthn, and biometric authentication are not implemented. Tests used
local HTTP with production cookie attributes verified separately over TestClient
HTTPS; a real TLS deployment has not been exercised. Browser evidence is Chromium
only. AI tests and a short real video run do not establish field detection accuracy.

The local runtime now requires login. The administrator password is held in
`secrets/admin_password` (owner-only permissions, excluded from Git). Other named
accounts can be created through User access. Before external deployment, validate
the actual HTTPS reverse proxy with login throttling. Keep Camera 3 as the sole
enabled live worker. A consistent database backup was taken before activation.
