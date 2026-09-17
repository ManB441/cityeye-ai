#!/usr/bin/env python3
"""Measure Camera 3 pacing at the VLC bridge, preview file, and MJPEG edge."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time
import urllib.request

import cv2


@dataclass
class Samples:
    times: list[float] = field(default_factory=list)
    hashes: list[bytes] = field(default_factory=list)
    error: str | None = None
    media_times_ms: list[float] = field(default_factory=list)

    def add(self, payload: bytes) -> None:
        self.times.append(time.monotonic())
        self.hashes.append(hashlib.blake2s(payload, digest_size=8).digest())

    def report(self, elapsed: float) -> dict[str, float | int | str | None]:
        intervals = [b - a for a, b in zip(self.times, self.times[1:])]
        ordered = sorted(intervals)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else 0
        unique = sum(a != b for a, b in zip(self.hashes, self.hashes[1:]))
        duplicates = len(self.hashes) - 1 - unique if len(self.hashes) > 1 else 0
        return {
            "frames": len(self.times),
            "fps": round(len(self.times) / elapsed, 2),
            "median_ms": round(statistics.median(intervals) * 1000, 1) if intervals else 0,
            "p95_ms": round(p95 * 1000, 1),
            "max_gap_ms": round(max(intervals, default=0) * 1000, 1),
            "gaps_gt_150ms": sum(value > 0.150 for value in intervals),
            "gaps_gt_250ms": sum(value > 0.250 for value in intervals),
            "gaps_gt_500ms": sum(value > 0.500 for value in intervals),
            "duplicate_rate": round(duplicates / max(1, len(self.hashes) - 1), 4),
            "unique_fps": round(unique / elapsed, 2),
            "error": self.error,
        }


def find_bridge_url(camera_path: str) -> str:
    processes = subprocess.run(
        ["ps", "-axo", "command="], check=True, capture_output=True, text=True
    ).stdout
    for command in processes.splitlines():
        if camera_path not in command or "dst=127.0.0.1:" not in command:
            continue
        match = re.search(r"dst=127\.0\.0\.1:(\d+)/camera\.ts", command)
        if match:
            return f"http://127.0.0.1:{match.group(1)}/camera.ts"
    raise RuntimeError(f"No VLC bridge found for {camera_path}")


def sample_bridge(url: str, end: float, samples: Samples) -> None:
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        while time.monotonic() < end:
            ok, frame = capture.read()
            if not ok or frame is None:
                samples.error = "bridge read failed"
                return
            gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 64))
            samples.add(gray.tobytes())
            samples.media_times_ms.append(capture.get(cv2.CAP_PROP_POS_MSEC))
    finally:
        capture.release()


def sample_file(path: Path, end: float, samples: Samples) -> None:
    last_mtime = -1
    while time.monotonic() < end:
        try:
            mtime = path.stat().st_mtime_ns
            if mtime != last_mtime:
                payload = path.read_bytes()
                if payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9"):
                    last_mtime = mtime
                    samples.add(payload)
        except FileNotFoundError:
            pass
        time.sleep(0.002)


def sample_mjpeg(url: str, end: float, samples: Samples) -> None:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            buffer = b""
            while time.monotonic() < end:
                chunk = response.read(4096)
                if not chunk:
                    samples.error = "MJPEG connection closed"
                    return
                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    finish = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                    if start < 0 or finish < 0:
                        buffer = buffer[-2_000_000:]
                        break
                    samples.add(buffer[start : finish + 2])
                    buffer = buffer[finish + 2 :]
    except Exception as exc:  # diagnostic output must preserve the edge error
        samples.error = str(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--camera-id", default="camera-3")
    parser.add_argument("--camera-path", default="live_ch02_0")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    bridge_url = find_bridge_url(args.camera_path)
    preview_path = Path(__file__).resolve().parents[1] / "ai" / "live_output" / args.camera_id / "preview.jpg"
    results = {name: Samples() for name in ("libvlc_bridge", "preview_jpeg", "backend_mjpeg")}
    started = time.monotonic()
    end = started + args.seconds
    threads = [
        threading.Thread(target=sample_bridge, args=(bridge_url, end, results["libvlc_bridge"])),
        threading.Thread(target=sample_file, args=(preview_path, end, results["preview_jpeg"])),
        threading.Thread(target=sample_mjpeg, args=(f"{args.backend}/media/live-cameras/{args.camera_id}/preview.mjpg", end, results["backend_mjpeg"])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=args.seconds + 15)
    elapsed = time.monotonic() - started
    print(f"elapsed_seconds={elapsed:.2f} bridge={bridge_url}")
    for name, samples in results.items():
        print(name, samples.report(elapsed))
        if name == "libvlc_bridge" and len(samples.media_times_ms) > 1:
            media_intervals = [
                b - a for a, b in zip(samples.media_times_ms, samples.media_times_ms[1:])
                if b > a
            ]
            print("libvlc_media_timestamps", {
                "nonzero_samples": sum(value > 0 for value in samples.media_times_ms),
                "median_ms": round(statistics.median(media_intervals), 1) if media_intervals else 0,
                "p95_ms": round(sorted(media_intervals)[min(len(media_intervals)-1, int(len(media_intervals)*0.95))], 1) if media_intervals else 0,
                "max_ms": round(max(media_intervals, default=0), 1),
            })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
