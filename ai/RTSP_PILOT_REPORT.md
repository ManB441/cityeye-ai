# CityEye AI RTSP / Live Camera Pilot Report

## Architecture

The AI worker now accepts a `FrameSource` contract with two implementations:

- `VideoFileSource`: deterministic file reads and video-relative timestamps.
- `RTSPFrameSource`: a background latest-frame reader with bounded reconnects.

RTSP decoding is selectable per camera. `OPENCV` remains the default for
standards-compliant modern cameras, `VLC` uses direct headless libVLC decoded
frame callbacks for legacy servers, and `AUTO` tries OpenCV before VLC. Decoder
adapters only open/decode frames; `RTSPFrameSource` continues to own health,
stale detection, reconnect/backoff, generation changes, and shutdown.

Both feed the unchanged YOLO/ByteTrack/event-rule processing loop. In RTSP mode,
the worker publishes the latest annotated JPEG, sanitized health, class metrics,
events, and evidence to `ai/live_output`. FastAPI exposes those server-side
outputs as JSON and MJPEG. The browser never connects to RTSP directly.

## Configuration and secrets

`ai/config/live_camera.json.example` documents the single-camera pilot. The
stream URL is resolved from `CITYEYE_RTSP_URL` by default. No real URL,
username, password, or token is committed. Log output masks URL userinfo.

Recommended deployment controls:

- read-only camera account;
- secrets injected by the service manager, not checked into JSON;
- camera reachable only from the municipal server/VPN;
- RTSP port blocked from public networks;
- rotate pilot credentials after demonstrations.

## Timestamp strategy

- Video files retain seconds relative to frame zero (`frame / source_fps`).
- RTSP frames use Unix wall-clock seconds captured after a successful read.
- Event details identify `VIDEO_SECONDS` or `WALL_CLOCK_UNIX` explicitly.

## Latency and reconnect behavior

RTSP capture runs in a background thread with a one-frame latest-frame buffer,
so slow inference drops stale intermediate frames instead of building latency.
Inference is capped by `inference_fps`. Open and read timeouts are configured
when supported by the OpenCV FFmpeg backend. Failed/stale reads transition
through `OFFLINE` and `RECONNECTING` with exponential backoff bounded by the
configured maximum.

A stream generation increments only after the first successfully decoded frame
of a connection. Generation changes recreate YOLO/ByteTrack, trajectory state,
and temporal event rules while retaining previously emitted events. Therefore,
track IDs, stopped timers, and wrong-way history cannot cross an outage.

The VLC adapter uses a fixed 12-picture reusable pool (bounded for H.264
reference-frame pressure) and publishes only the latest
completed BGR frame. Linux uses RV32/BGRA callbacks; macOS uses software-decoded
I420 callbacks because VLC 3 VideoToolbox did not copy usable RV32 pixels for
the verified legacy DVR. Opaque picture tokens are real, strongly referenced
native pointers retained until the matching display callback. The adapter does
not launch a GUI, restream, encode JPEG, write decoded frames to disk, or create
an unbounded queue. VLC callbacks never run inference.

## Frontend approach

The Municipal Dashboard retains all existing file scenarios and adds one small
`RTSP Camera` source card. The live feed uses server-generated MJPEG, while
status, FPS, counts, traffic state, events, and review actions use the existing
two-second polling style. The page displays `ONLINE`, `OFFLINE`, or
`RECONNECTING` and does not expose the RTSP URL.

## Verification

- AI tests: 152 passed after the final VLC callback lifecycle refinement.
- Backend tests: 116 passed, including live health/metrics/events/MJPEG tests.
- Frontend tests and TypeScript/Vite production build pass in final verification.
- File regression: processed three frames from `sample_videos/traffic.mp4` and
  produced MP4, CSV, and events output through `VideoFileSource`.
- Local RTSP end-to-end: MediaMTX + FFmpeg published the existing sample video;
  CityEye decoded and processed five inference frames, generated a current
  annotated JPEG and metrics, and exited cleanly at `--max-frames 5`.
- A live outage probe observed explicit `RECONNECTING` and `OFFLINE` states.
  Deterministic tests cover generation-change reset semantics.
- Real legacy DVR Camera 3: direct libVLC callbacks delivered changing frames at
  944x1090, remained `ONLINE`, and shut down cleanly. A measurement received 30
  frames at about 11 decoded frames/second, with maximum observed frame age of
  4.7 ms and about 135 MB process peak RSS on the M1 host. A 30-frame run passed
  through the existing YOLO/ByteTrack loop and published the latest processed
  image, metrics, tracks CSV, and events JSON. The static/partially visible van
  in that sample did not meet the unchanged production detector threshold, so
  that run produced no track IDs; ingestion success is confirmed, while a scene
  containing clearly visible moving road users is still needed to validate real
  Camera 3 tracking IDs.

No production model, detector thresholds, tracker YAML, event thresholds, or
default `VIDEO_FILE` configuration was changed by this RTSP task.

## Known limitations and pilot risks

- **P0:** None identified in the implemented single-camera path.
- **P1:** Run a longer camera-specific soak test, including repeated physical
  camera/network outages, before unattended municipal use. RTSP behavior and
  OpenCV timeout support vary by camera codec, firmware, and FFmpeg build.
- **P1:** Legacy VLC capture requires native libVLC and plugins in addition to
  the `python-vlc` binding. Container and host library discovery must be checked
  during deployment.
- **P1:** Docker Desktop's local containerd store returned an I/O error after an
  earlier dependency resolution pulled an unnecessary CUDA image. The Dockerfile
  now installs CPU-only PyTorch first, but Docker Desktop must be repaired or
  restarted before the corrected image build can be verified locally.
- **P1:** MJPEG is suitable for one pilot dashboard but is bandwidth-heavy and
  not the final multi-viewer transport. Consider HLS/WebRTC after the pilot.
- **P2:** Health and frames are filesystem snapshots for one local worker; a
  production multi-instance deployment needs shared state or sticky routing.
- **P2:** The API has no authentication/authorization layer in this MVP. Keep it
  on a trusted pilot network until municipal identity controls are added.
- **P3:** Processing FPS is cumulative and intentionally approximate; add a
  rolling latency/FPS window for operations dashboards later.
