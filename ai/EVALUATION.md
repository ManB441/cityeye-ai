# CityEye AI evaluation harness

This harness measures existing pipeline outputs and compares detector variants
without changing production configuration or model weights.

## Existing output audit

Pass the matching scenario config so vehicle ROI counts are calculated from the
recorded bounding-box centers. Without a config, `vehicles_in_roi` is `null`
rather than guessed.

```bash
cd ai
.venv/bin/python evaluation.py outputs \
  outputs/congestion \
  --config config/scenarios/congestion.json \
  --json /tmp/cityeye-congestion-output.json
```

## Detector benchmark

The benchmark compares the current production configuration, a lower raw
confidence threshold at 1280 pixels, YOLOv8s on the full frame, and YOLOv8s on
the configured road crop. Its frame-level `tracked_objects` field is expected
to be zero because isolated-frame detection does not run ByteTrack; tracked
object counts must be taken from the existing-output audit or a full video run.
Each unique model/input-shape combination receives one untimed warm-up inference
before performance samples are collected.

```bash
.venv/bin/python evaluation.py benchmark \
  --video samples/congestion.mp4 \
  --config config/scenarios/congestion.json \
  --timestamps 2 6 10 \
  --variants A-production B-yolov8n-1280-low-conf \
  --output /tmp/cityeye-congestion-benchmark.json
```

## Manual ground truth

Precision, recall, TP, FP, and FN are emitted only when explicit manual
annotations are supplied. Copy `evaluation_ground_truth.example.json` and add
entries with this shape:

```json
{
  "frames": [
    {
      "video": "source-file.mp4",
      "frame_index": 120,
      "annotations": [
        {"class_name": "car", "box": [100, 100, 200, 200]}
      ]
    }
  ]
}
```

Boxes use source-frame pixel coordinates in `[x1, y1, x2, y2]` order. Allowed
classes are `person`, `bicycle`, `car`, `motorcycle`, `bus`, and `truck`.
Never use the empty example file as evidence of detection quality.
