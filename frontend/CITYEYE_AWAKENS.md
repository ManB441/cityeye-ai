# CityEye Awakens — implementation and acceptance

This change replaces only the login presentation. The existing auth hook, cookie
session mechanism, backend/RBAC, AI, Camera 3, analytics and incident logic remain
unchanged. No new dependency was installed. No commit or push was made.

## Files and reusable pieces

- `src/components/login/CityEyeVisual.tsx`: reusable SVG eye with an explicit
  idle/verifying/success/failure phase. Road-shaped contours, branching paths,
  junction nodes, 72 sensor ticks, orbiting arcs, counter-rotating rings, and a
  dark pupil with a small cyan point. Decorative annotations describe the product,
  never invented runtime health or telemetry. Decorative SVG is hidden from AT.
- `src/components/login/CityNetworkBackground.tsx`: sparse abstract road map,
  intersections, a few beacon pulses, and only two traveling signals.
- `src/components/login/SecureLoginPanel.tsx`: accessible inputs, visibility toggle,
  existing safe error, current request/success announcements, and integrated right
  section. Username compatibility remains through the existing username field;
  visible copy says Email and mobile keyboards use email input mode.
- `src/components/login/useCityEyeMotion.ts`: reduced-motion subscription and
  pointer animation lifecycle, independent from authentication.
- `src/pages/LoginPage.tsx`: composition and presentation state machine around the
  unchanged `auth.login` promise, plus routing after confirmed success.
- `src/login-awakens.css`: scoped appearance, animation and responsive rules.
- `src/pages/LoginPage.test.tsx`: four new success-gating, failure, reduced-motion
  and timer-cleanup tests.
- `src/App.test.tsx`: revised heading assertions and an explicit async wait for
  existing traffic data to settle before checking metrics.

## Motion and interaction

Pointer direction is calculated from the cached eye center. The iris offset is
limited to 14 SVG units; exponential interpolation uses elapsed frame time for
consistent easing. Eye parallax stays below five pixels; background parallax below
three. Pointer movement writes CSS custom properties directly, not React state.
A single requestAnimationFrame chain runs while the eye settles and then sleeps.
Geometry is measured on resize/scroll, not on every pointer event. Nearby network
intersections/segments highlight by distance; there is no cursor glow or custom
cursor. A secondary iris ring responds slightly to the viewing direction.

Email focus illuminates sensor brackets. Password focus contracts the core and
activates the surrounding ring. Button hover adds a restrained sweep and arrow
movement; pointer-down compresses the button and intensifies inward trajectories.
These are decorative interactions, not claims of biometric verification.

The staggered entrance builds the sensor and road contours, then branding,
headline and integrated form. It settles explicitly after 1.7 seconds and retires
completed animation layers. Form controls are never blocked by an intro overlay.
The form submits immediately through the existing auth hook.

During the real request, the button/status says Verifying access and the eye turns
toward the form. Only a successful auth promise with the confirmed user enables
Identity verified, followed after 260ms by Access granted. Rings align, the core
pulses, a scan crosses the sensor, and a single wave expands. Navigation happens
720ms after success, preserving the existing protected-route return destination.
A pre-existing restored session skips this sequence. Failed attempts receive a
muted amber pulse/refocus and the existing generic error; the eye settles after
1.2 seconds without erasing the form.

All listeners, timers, ResizeObserver subscriptions and RAF callbacks clean up on
unmount. No WebGL, video background, external fonts, image downloads, or animation
library is required. Primary continuous animation uses transform and opacity;
only the few traveling SVG signals use stroke-dashoffset.

## Responsive and accessibility behavior

Desktop/laptop show the five-line headline, large eye and separated access section.
At 900px and below, the composition becomes a centered brand, small eye and form;
background detail is reduced. Touch/coarse pointers do not drive the eye.

Reduced motion disables tracking, parallax, rotation, traveling signals, entrance
animation and wave transition. Successful login navigates immediately. Focus
indicators and status messages remain useful without motion.

Inputs retain autocomplete, accessible labels, Enter submission and password
visibility. Keyboard focus is visible. The form exposes busy state; errors use
role=alert and request/result feedback uses a polite atomic live region. No
protected application content is mounted beneath the login page.

## Validation

Baseline: 35 frontend tests plus real-browser successful login, invalid login,
logout, refresh restoration and anonymous protected-route redirect.

After redesign: 39 frontend tests pass and the production build passes. The same
real-browser auth sequence passes on the deployed frontend, including Camera 3
preview access after login. All 46 backend auth tests pass against isolated test databases.
The backend/auth/session/AI source checksums match the start of this task.
`git diff --check` passes. Only the frontend container was rebuilt/recreated.

Visual acceptance checks use Chromium on the current MacBook at 1440×900,
1280×800, 1024×768, 768×1024, 390×844 and 320×740. The eye and headline were inspected
in screenshots, pointer movement and network response checked in-browser, and
reduced-motion styles verified. The intro completion marker ensures finite
entrance animations cannot leave the headline hidden during resize.

Limits: Chromium was tested; Safari and Firefox were not. Local frame timing is
not a guarantee of 60 FPS across hardware, CPU load, or browser implementations.
Brand geometry uses vector strokes and system typography, not a custom font.
There is no biometric authentication or new backend functionality in this change.

Measured locally with the animated page and simulated pointer movement: median
requestAnimationFrame interval 16.7ms (approximately 60 FPS), 95th percentile
50ms under the current machine load. This indicates occasional dropped frames,
not a locked 60 FPS claim. The pointer RAF queue reached zero after settling.
