# Camera 3 — read-only image / AI input diagnostic

**Finding:** today's daylight source is usable for limited detection and tracking. The severe blur in the earlier calibration image is real, but is condition-dependent. Evidence points toward poor night source imagery; the precise optical/exposure/DVR cause remains **UNDETERMINED**. No production code, configuration, model, tracker, thresholds, ROI or event behavior was changed, and the worker was not restarted.

## Captured evidence and scope

- Capture UTC: 2026-09-18T09:05:38.141012+00:00 to 2026-09-18T09:05:44.783758+00:00; generation 37.
- Passively copied four seconds of the **existing local VLC remux**, preserving compressed H.264 packets. No extra DVR/RTSP connection was created.
- Analyzed **20 consecutive decoded frames**, spanning **1.561 seconds** of media PTS. This is a short scene sample, not a reliability trial.
- Frame size **944×1080**, BGR. Codec reports coded height 1088 and displayed height 1080; both decoders output 1080. Advertised frame-rate metadata is unreliable, so frame timing is taken from PTS (approximately 59–120 ms between these frames).
- Per-frame PTS, decode timestamps, size, generation context, content change, statistics, boxes/confidences and tracker output are embedded in [report.json](report.json). Exposure UTC/live-worker frame sequence cannot be recovered exactly for each passive frame; decode time is not presented as capture time.
- Concurrently preserved **66 live preview JPEGs and 26 live AI-output JPEGs**, including their neighboring status/metrics snapshots.

## SOURCE

**Is the source changing? YES.** Zero exact duplicate pairs out of 19: **0.0% duplicate rate**. Mean consecutive BGR absolute difference is **0.251/255**. Minor changes can include sensor/codec noise or OSD; this does not establish vehicle motion.

**Is it visually usable?** The present daylight frame shows a road and three identifiable cars: a partly cropped silver car at left, a green car at top and a partly occluded blue car at upper right. The previous night view does not provide comparable detail. No road boundaries or permitted direction have been inferred or approved.

## IMAGE QUALITY

- Mean grayscale brightness: **145.95/255**, versus **90.06** in the archived night baseline.
- Contrast (grayscale standard deviation): **39.84**, versus **17.69** at night.
- Saturation: mean **30.27/255**, std **21.05**; detailed percentiles per frame are in JSON.
- Interior Laplacian variance: **78.18**, versus **0.882** at night. The fixed statistics-only interior excludes the top 70/bottom 100/side 20 pixels to avoid DVR text dominating sharpness. This is not a traffic ROI. Full-frame values are also retained. These values compare these samples, not a universal pass/fail blur threshold.
- Bright gray pixels ≥245: **1.40%**; all BGR channels ≥250: **1.03%**. Current road reflections cause local glare, not a globally white/overexposed frame.
- The archived night baseline is severely veiled/blurred despite sharp DVR captions. Its very-bright fraction is only **0.108%**; global overexposure is not supported. A second archived night frame shows diffuse headlight-like bloom. Exact cause—focus, cover/lens condition, IR reflection or exposure/denoising—is not established.
- **Resolution sufficiency:** enough for these three daytime detections; not proof of general coverage. The green car is about 80×74 pixels and the blue car only about 25×87 pixels. Framing/cropping and distance limit available detail.

## PIPELINE — direct source → AI input → YOLO → ByteTrack

1. **Source decoding:** same encoded stream decoded with OpenCV (production decode path) and a separate FFmpeg CLI decode using passthrough timing. Maximum channel difference **3 /255**, maximum frame mean difference **1.207/255**. No spatial/color corruption or severe blur introduced by either current decoder is evident. These use different decoder builds but both are FFmpeg-based, not two wholly independent codec implementations.
2. **I420:** the actual macOS worker uses VLC as a local MPEG-TS remux, then OpenCV decodes. The custom `VLCI420FrameBuffer` callback/conversion path is not running. H.264 `yuv420p` does not mean that custom callback is active.
3. **JPEG:** reproducing the existing preview quality 75 on these exact decoded images gives mean **40.53 dB PSNR**. The mild compression loss is measurable and does not resemble the previous severe scene blur.
4. **Actual live output:** nearest concurrent production preview matches have interior mean difference **1.53–1.61/255**; production AI-output images **1.45–1.63/255** after excluding header/footer annotations. Both show the same scene. These are nearest-image comparisons, not proof of identical exposure/frame ID.
5. **Exact AI-input replay:** all 20 arrays tapped at YOLO's actual preprocess boundary in an isolated replay are byte-identical to their captured decoded raw frames: **maximum difference 0**. Saved `ai-input-01/10/20` files come from that tap. They are **not dumps attached to the running production worker**; its recorder remains disabled. Architecture does not expose exact production input identity read-only.
6. Network input is **[1,3,960,864]** after normal letterboxing/resizing, RGB conversion and normalization. The preprocessed tensor visualization is saved as `yolo-network-input-01.jpg`.

The replay uses every captured source frame, whereas the live scheduler normally skips frames to its AI rate. Replay tracker IDs/cadence are not claimed identical to the worker's. Current production counts provide a separate cross-check.

## YOLO

Current **yolov8n.pt**, confidence **0.22**, image size **960**, IoU **0.7**, existing supported classes and existing `bytetrack_cityeye.yaml`. Model SHA-256 and exact arguments are retained in JSON.

**Vehicles visible? YES. Detected? YES.** Three cars detected in every frame. Across all 20 frames confidence is **0.254–0.883**:

- Left partial silver car: approximately **0.872–0.883**.
- Upper green car: approximately **0.727–0.799**.
- Upper-right partial blue car: approximately **0.254–0.301**.

Example frame 10 detector boxes, in original pixels:

- car **0.881**, `(1.27,254.56)–(66.56,491.61)`.
- car **0.799**, `(306.99,14.33)–(386.62,88.36)`.
- car **0.298**, `(708.69,123.36)–(733.68,210.70)`.

There are 60 frame-level detections, representing three repeatedly observed cars, **not 60 vehicles**. All classes/confidences/boxes for every frame are in JSON.

The separate diagnostic-only supported `predict(conf=0.01)` pass produces **26–40 candidate boxes/frame**, including weak/overlapping upper-edge/clutter boxes. They are unverified candidates, not extra confirmed vehicles or justification to lower production thresholds. The production setting stayed 0.22.

## TRACKING

**Do detections reach ByteTrack? YES.** An ephemeral wrapper around the real `BYTETracker.update` in the isolated replay recorded all three incoming detector boxes and all three returned tracks for every frame. No boxes were lost there or in the subsequent production confidence filter for this sample. Concurrent running-worker metrics also report **3 vehicles / 3 tracks**.

Below-0.22 candidates from the separate low-confidence experiment are outside production inference; they are not examples of ByteTrack suppression. Moving traffic, crowded scenes and night tracking are not validated here.

## ROOT CAUSE — evidence-backed categories

- **CAMERA_QUALITY:** supported at the source-image/lighting-condition level, **moderate confidence** for explaining the old night failure. The old scene is diffuse while embedded DVR captions are sharp; current daytime content and detections are clear through the existing unchanged pipeline.
- **UNDETERMINED:** exact night failure mechanism remains unresolved. There is no simultaneous native DVR view or pre-JPEG night bitstream from the old failure.
- **SOURCE_PIPELINE / IMAGE_CONVERSION / JPEG_ENCODING / BYTETRACK:** no evidence of a severe fault in this captured daytime sample. An intermittent historical failure cannot be absolutely excluded from current evidence alone.
- **YOLO_RECALL:** not supported as the reason these three clearly visible current cars were missing—they are detected. Broader/night recall is not established.
- **NO_VISIBLE_VEHICLES:** false for the current sample; historical obscured vehicle presence is undetermined.
- **CAMERA_ANGLE:** observed edge cropping and small distant objects limit detail, but angle is not demonstrated to cause the old uniform veil. No geometry change is proposed in this diagnostic.

**Confidence is HIGH** that the current sampled scene reaches detection/tracking without severe CityEye degradation; **MODERATE** that night source image quality explains the earlier issue; **UNDETERMINED** for its physical mechanism.

## Single next action

**When the bad night condition recurs, capture the native DVR display and this passive CityEye source stream simultaneously.** Compare them before changing any camera, model, tracker or threshold setting. This distinguishes upstream night image degradation from an intermittent software-path problem.

## Hackathon decision

**Conditionally usable for a daylight live-view/basic detection-tracking demo**, supported by these three parked/partial cars. **Not demonstrated reliable at night, with moving traffic, or for spatial events.** Camera 3's existing CALIBRATION_REQUIRED state is unchanged. This investigation does not create/approve an ROI or validate event algorithms.

## Artifacts and cleanup

[Raw 01](raw-01.jpg), [raw 10](raw-10.jpg), [raw 20](raw-20.jpg); [AI input 01](ai-input-01.jpg), [AI input 10](ai-input-10.jpg), [AI input 20](ai-input-20.jpg); [YOLO boxes, frame 10](yolo-output-10.jpg); [4× green-car crop](green-car-crop-10.jpg). Crop is nearest-neighbor enlargement for inspection only, with no detail recovery or calibration meaning.

Lossless decoded arrays and PNG representatives, encoded `source-packets.ts`, independent decoder images, production JPEG snapshots, pixel comparisons and complete predictions are retained locally. [Previous night baseline](previous-night-raw.jpg) and [night bloom example](previous-night-glare.jpg) are copies of existing diagnostic evidence.

Production file/config SHA-256 checks: **all unchanged**. No restart, persistent hook, production instrumentation, new feature or ROI. Temporary wrappers restored in `finally`; replay exited and capture connections closed. Helper scripts in `/tmp` were removed at completion. No commit or push. No production regression suite rerun was necessary for this read-only investigation; evidence consistency checks passed.
