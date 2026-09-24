#!/usr/bin/env python3
"""Read-only preflight for local recorded-video inputs; never downloads weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "ai/config/scenarios/maydan_palestine.json")
    parser.add_argument("--ai-root", type=Path, default=ROOT / "ai")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
    except (OSError, ValueError):
        print(f"FAIL: provide a readable JSON camera configuration with --config: {args.config}", file=sys.stderr)
        return 1
    if not isinstance(config, dict) or config.get("source_type", "VIDEO_FILE") != "VIDEO_FILE":
        print("FAIL: this preflight accepts recorded VIDEO_FILE configurations only", file=sys.stderr)
        return 1
    paths = {}
    errors = []
    for key, label in (("video_source", "video"), ("model", "model weights")):
        value = config.get(key, "yolov8n.pt" if key == "model" else None)
        if not isinstance(value, str) or not value.strip() or "://" in value:
            errors.append(f"Set {key} to a local file path in the configuration")
            continue
        path = Path(value)
        if not path.is_absolute():
            path = args.ai_root / path
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"Missing {label}: {path}. Supply the approved local asset before inference; no download was attempted.")
        else:
            paths[key] = path
    profile = config.get("recorded_calibration")
    if profile is not None:
        expected = profile.get("source_sha256") if isinstance(profile, dict) else None
        if not isinstance(expected, str) or len(expected) != 64:
            errors.append("Recorded calibration requires a valid source_sha256")
        elif "video_source" in paths:
            digest = hashlib.sha256()
            with paths["video_source"].open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                errors.append("Video SHA-256 does not match recorded calibration; provide the exact calibrated source")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: local config, nonempty video/weights, and configured source hash. Decode, model compatibility and geometry still require pipeline validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
