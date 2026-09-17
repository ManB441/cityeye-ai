"""Frame-source abstraction for deterministic files and resilient RTSP streams."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
from enum import Enum
import importlib
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Callable
from collections import deque

import cv2
import numpy as np


class SourceType(str, Enum):
    VIDEO_FILE = "VIDEO_FILE"
    RTSP = "RTSP"


class CaptureBackend(str, Enum):
    OPENCV = "OPENCV"
    VLC = "VLC"
    AUTO = "AUTO"


class CameraState(str, Enum):
    ONLINE = "ONLINE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    RECONNECTING = "RECONNECTING"


@dataclass(frozen=True)
class FramePacket:
    frame: np.ndarray
    frame_index: int
    timestamp: float
    generation: int = 0


@dataclass
class CameraHealth:
    camera_id: str
    source_type: SourceType
    state: CameraState = CameraState.OFFLINE
    last_frame_at: float | None = None
    last_connected_at: float | None = None
    last_error: str | None = None
    processing_fps: float = 0.0
    ai_inference_fps: float = 0.0
    reconnect_attempts: int = 0
    generation: int = 0
    dropped_frames: int = 0
    heartbeat_at: float | None = None
    last_visual_change_at: float | None = None
    callback_sequence: int = 0
    visual_sequence: int = 0
    consecutive_similar_frames: int = 0
    camera_capture_fps: float = 0.0
    preview_publication_fps: float = 0.0
    preview_last_frame_at: float | None = None
    buffer_pressure: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["source_type"] = self.source_type.value
        payload["state"] = self.state.value
        return payload


def parse_source_type(value: object) -> SourceType:
    try:
        return SourceType(str(value or SourceType.VIDEO_FILE.value).upper())
    except ValueError as exc:
        raise ValueError("source_type must be VIDEO_FILE or RTSP") from exc


def parse_capture_backend(value: object) -> CaptureBackend:
    if isinstance(value, CaptureBackend):
        return value
    try:
        return CaptureBackend(str(value or CaptureBackend.OPENCV.value).upper())
    except ValueError as exc:
        raise ValueError("capture_backend must be OPENCV, VLC, or AUTO") from exc


def mask_stream_url(value: str) -> str:
    """Remove user/password material while preserving useful host/path context."""
    return re.sub(r"(rtsp://)[^/@]+@", r"\1***:***@", value, count=1)


def resolve_rtsp_url(config: dict, environ: dict[str, str] | None = None) -> str:
    environ = environ or os.environ
    variable = str(config.get("rtsp_url_env", "")).strip()
    direct = str(config.get("rtsp_url", "")).strip()
    url = environ.get(variable, "").strip() if variable else direct
    if not url:
        raise ValueError("RTSP URL is missing; configure rtsp_url_env or local rtsp_url")
    if not url.lower().startswith("rtsp://"):
        raise ValueError("RTSP URL must start with rtsp://")
    return url


class VisualFreshnessTracker:
    """Detect an armed decoder that keeps returning near-identical source pixels."""

    def __init__(
        self,
        *,
        difference_threshold: float = 0.08,
        stale_after_seconds: float = 15.0,
        minimum_similar_frames: int = 30,
        changes_to_arm: int = 3,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.difference_threshold = float(difference_threshold)
        self.stale_after_seconds = float(stale_after_seconds)
        self.minimum_similar_frames = int(minimum_similar_frames)
        self.changes_to_arm = int(changes_to_arm)
        self.clock = clock
        self.callback_sequence = 0
        self.visual_sequence = 0
        self.consecutive_similar_frames = 0
        self.last_callback_at: float | None = None
        self.last_visual_change_at: float | None = None
        self.last_difference = 0.0
        self._previous: np.ndarray | None = None

    @property
    def armed(self) -> bool:
        return self.visual_sequence >= self.changes_to_arm

    def observe(self, frame: np.ndarray, timestamp: float | None = None) -> bool:
        now = self.clock() if timestamp is None else timestamp
        sample = cv2.resize(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
            (64, 64),
            interpolation=cv2.INTER_AREA,
        )
        self.callback_sequence += 1
        self.last_callback_at = now
        changed = self._previous is None
        if self._previous is not None:
            self.last_difference = float(
                np.mean(cv2.absdiff(sample, self._previous))
            )
            changed = self.last_difference >= self.difference_threshold
        self._previous = sample
        if changed:
            self.visual_sequence += 1
            self.last_visual_change_at = now
            self.consecutive_similar_frames = 0
        else:
            self.consecutive_similar_frames += 1
        return changed

    def is_stuck(self, timestamp: float | None = None) -> bool:
        now = self.clock() if timestamp is None else timestamp
        return bool(
            self.armed
            and self.last_visual_change_at is not None
            and now - self.last_visual_change_at >= self.stale_after_seconds
            and self.consecutive_similar_frames >= self.minimum_similar_frames
        )


class VideoFileSource:
    """Deterministic local-file source preserving video-relative timestamps."""

    def __init__(self, path: Path, capture_factory: Callable = cv2.VideoCapture) -> None:
        self.path = Path(path)
        self.capture = capture_factory(str(self.path))
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open video: {self.path}")
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_index = 0
        self.health = CameraHealth(
            camera_id="video-file",
            source_type=SourceType.VIDEO_FILE,
            state=CameraState.ONLINE,
            last_connected_at=time.time(),
        )

    def read(self, timeout: float | None = None) -> FramePacket | None:
        del timeout
        ok, frame = self.capture.read()
        if not ok:
            return None
        timestamp = self.frame_index / self.fps if self.fps > 0 else 0.0
        packet = FramePacket(frame, self.frame_index, timestamp)
        self.frame_index += 1
        self.health.last_frame_at = time.time()
        return packet

    def close(self) -> None:
        self.capture.release()
        self.health.state = CameraState.OFFLINE


class VLCFrameBuffer:
    """Small reusable RV32 pool that publishes only complete newest frames."""

    # Legacy H.264 streams may retain several reference pictures internally.
    # Keep a fixed, bounded pool large enough that libVLC never has to block
    # its decoder waiting for a display callback to release one of three frames.
    BUFFER_COUNT = 12

    def __init__(self) -> None:
        self.width = 0
        self.height = 0
        self.pitch = 0
        self._native_buffers: list[object] = []
        self._drop_buffer: object | None = None
        self._retired_native_buffers: list[object] = []
        self._buffer_epoch = 0
        self._next_token = 1
        self._active_tokens: dict[int, tuple[object, int, int]] = {}
        self._available: list[int] = []
        self._condition = threading.Condition()
        self._ready: tuple[int, int] | None = None
        self._sequence = 0
        self._consumed_sequence = 0
        self._closed = False
        self._dropped_frames = 0

    def configure(self, width: int, height: int) -> int:
        if width <= 0 or height <= 0:
            raise ValueError("VLC returned invalid video dimensions")
        pitch = ((width * 4 + 31) // 32) * 32
        with self._condition:
            if self._native_buffers:
                self._retired_native_buffers.append(self._native_buffers)
            self._buffer_epoch += 1
            self.width = width
            self.height = height
            self.pitch = pitch
            buffer_type = ctypes.c_ubyte * (pitch * height)
            self._native_buffers = [buffer_type() for _ in range(self.BUFFER_COUNT)]
            self._drop_buffer = buffer_type()
            self._available = list(range(self.BUFFER_COUNT))
        return pitch

    @property
    def pitches(self) -> tuple[int, ...]:
        return (self.pitch,)

    @property
    def lines(self) -> tuple[int, ...]:
        return (self.height,)

    @property
    def native_pointer(self) -> ctypes.c_void_p:
        if not self._native_buffers:
            return ctypes.c_void_p()
        return ctypes.cast(self._native_buffers[0], ctypes.c_void_p)

    def acquire(self) -> tuple[int, ctypes.c_void_p]:
        with self._condition:
            if self._closed or not self._native_buffers:
                return 0, ctypes.c_void_p()
            if not self._available:
                self._dropped_frames += 1
                return 0, ctypes.cast(self._drop_buffer, ctypes.c_void_p)
            index = self._available.pop(0)
            token_value = self._next_token
            self._next_token += 1
            token_object = ctypes.c_uint64(token_value)
            token = ctypes.addressof(token_object)
            self._active_tokens[token] = (
                token_object, self._buffer_epoch, index
            )
            return token, ctypes.cast(
                self._native_buffers[index], ctypes.c_void_p
            )

    @property
    def dropped_frames(self) -> int:
        with self._condition:
            return self._dropped_frames

    def acquire_planes(self) -> tuple[int, tuple[ctypes.c_void_p, ...]]:
        token, pointer = self.acquire()
        return token, (pointer,)

    def publish(self, token: int = 1) -> None:
        with self._condition:
            active = self._active_tokens.pop(int(token), None)
            if active is None:
                return
            _token_object, epoch, index = active
            if (
                self._closed
                or epoch != self._buffer_epoch
                or index < 0
                or index >= len(self._native_buffers)
                or index in self._available
            ):
                return
            if self._ready is not None:
                previous_epoch, previous_index = self._ready
                if previous_epoch == self._buffer_epoch:
                    self._available.append(previous_index)
            self._ready = (epoch, index)
            self._sequence += 1
            self._condition.notify_all()

    def _copy_frame(self, index: int) -> np.ndarray:
        rows = np.ctypeslib.as_array(self._native_buffers[index]).reshape(
            self.height, self.pitch
        )
        # RV32 on little-endian platforms is BGRX/BGRA.
        return rows[:, : self.width * 4].reshape(
            self.height, self.width, 4
        )[:, :, :3].copy()

    def read(self, timeout: float) -> np.ndarray | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._closed and self._sequence <= self._consumed_sequence:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if (
                self._closed
                or self._ready is None
                or self._sequence <= self._consumed_sequence
            ):
                return None
            self._consumed_sequence = self._sequence
            epoch, index = self._ready
            self._ready = None
        try:
            return self._copy_frame(index) if epoch == self._buffer_epoch else None
        finally:
            with self._condition:
                if epoch == self._buffer_epoch and index not in self._available:
                    self._available.append(index)
                    self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def cleanup_retired(self) -> None:
        """Release buffers only after libVLC declares the old format unused."""
        with self._condition:
            self._retired_native_buffers.clear()
            self._active_tokens = {
                token: active
                for token, active in self._active_tokens.items()
                if active[1] == self._buffer_epoch
            }


class VLCI420FrameBuffer(VLCFrameBuffer):
    """Reusable three-plane I420 pool for VLC software decoding on macOS."""

    def configure(self, width: int, height: int) -> int:
        if width <= 0 or height <= 0 or width % 2 or height % 2:
            raise ValueError("VLC returned invalid I420 video dimensions")
        y_pitch = ((width + 31) // 32) * 32
        uv_width, uv_height = width // 2, height // 2
        uv_pitch = ((uv_width + 31) // 32) * 32
        y_lines = ((height + 31) // 32) * 32
        uv_lines = ((uv_height + 31) // 32) * 32
        with self._condition:
            if self._native_buffers:
                self._retired_native_buffers.append(self._native_buffers)
            self._buffer_epoch += 1
            self.width, self.height, self.pitch = width, height, y_pitch
            self._plane_pitches = (y_pitch, uv_pitch, uv_pitch)
            self._plane_lines = (y_lines, uv_lines, uv_lines)
            self._native_buffers = [
                tuple(
                    (ctypes.c_ubyte * (pitch * lines))()
                    for pitch, lines in zip(
                        self._plane_pitches, self._plane_lines
                    )
                )
                for _ in range(self.BUFFER_COUNT)
            ]
            self._drop_buffer = tuple(
                (ctypes.c_ubyte * (pitch * lines))()
                for pitch, lines in zip(self._plane_pitches, self._plane_lines)
            )
            self._available = list(range(self.BUFFER_COUNT))
        return y_pitch

    @property
    def pitches(self) -> tuple[int, ...]:
        return self._plane_pitches

    @property
    def lines(self) -> tuple[int, ...]:
        return self._plane_lines

    @property
    def native_pointer(self) -> ctypes.c_void_p:
        if not self._native_buffers:
            return ctypes.c_void_p()
        return ctypes.cast(self._native_buffers[0][0], ctypes.c_void_p)

    def acquire_planes(self) -> tuple[int, tuple[ctypes.c_void_p, ...]]:
        with self._condition:
            if self._closed or not self._native_buffers:
                return 0, (ctypes.c_void_p(),) * 3
            if not self._available:
                self._dropped_frames += 1
                return 0, tuple(
                    ctypes.cast(plane, ctypes.c_void_p)
                    for plane in self._drop_buffer
                )
            index = self._available.pop(0)
            token_value = self._next_token
            self._next_token += 1
            token_object = ctypes.c_uint64(token_value)
            token = ctypes.addressof(token_object)
            self._active_tokens[token] = (
                token_object, self._buffer_epoch, index
            )
            return token, tuple(
                ctypes.cast(plane, ctypes.c_void_p)
                for plane in self._native_buffers[index]
            )

    def publish(self, token: int = 1) -> None:
        super().publish(token)

    def _copy_frame(self, index: int) -> np.ndarray:
        visible_sizes = (
            (self.height, self.width),
            (self.height // 2, self.width // 2),
            (self.height // 2, self.width // 2),
        )
        visible_planes = []
        for plane, pitch, lines, (visible_h, visible_w) in zip(
            self._native_buffers[index],
            self._plane_pitches,
            self._plane_lines,
            visible_sizes,
        ):
            rows = np.ctypeslib.as_array(plane).reshape(lines, pitch)
            visible_planes.append(rows[:visible_h, :visible_w].reshape(-1))
        packed = np.concatenate(visible_planes).reshape(
            self.height * 3 // 2, self.width
        )
        return cv2.cvtColor(packed, cv2.COLOR_YUV2BGR_I420)


class VLCFrameCapture:
    """cv2-like, headless libVLC adapter using direct decoded-frame callbacks."""

    def __init__(
        self,
        url: str,
        frame_timeout_seconds: float,
        network_caching_ms: int = 200,
        rtsp_tcp: bool = False,
        vlc_module=None,
        pixel_format: str | None = None,
    ) -> None:
        self.url = url
        self.frame_timeout = frame_timeout_seconds
        self.network_caching_ms = network_caching_ms
        self.rtsp_tcp = rtsp_tcp
        self._vlc = vlc_module or importlib.import_module("vlc")
        self.pixel_format = pixel_format or (
            "I420" if sys.platform == "darwin" else "RV32"
        )
        if self.pixel_format not in {"RV32", "I420"}:
            raise ValueError("VLC pixel_format must be RV32 or I420")
        self._buffer = (
            VLCI420FrameBuffer()
            if self.pixel_format == "I420"
            else VLCFrameBuffer()
        )
        self._instance = None
        self._media = None
        self._player = None
        self._opened = False
        self._released = False
        self._playback_error = threading.Event()
        self._callbacks: list[object] = []
        self._open()

    def _decorate(self, name: str, callback):
        decorators = getattr(self._vlc, "CallbackDecorators", None)
        decorator = getattr(decorators, name, None) if decorators else None
        return decorator(callback) if decorator else callback

    def _open(self) -> None:
        try:
            instance_options = [
                "--intf=dummy",
                "--no-audio",
                "--no-video-title-show",
                "--no-osd",
            ]
            if self.pixel_format == "I420":
                instance_options.extend(
                    [
                        "--codec=avcodec",
                        "--avcodec-hw=none",
                    ]
                )
            self._instance = self._vlc.Instance(*instance_options)
            self._media = self._instance.media_new(self.url)
            self._media.add_option(":no-audio")
            if self.rtsp_tcp:
                self._media.add_option(":rtsp-tcp")
            self._media.add_option(f":network-caching={self.network_caching_ms}")
            self._player = self._instance.media_player_new()
            self._player.set_media(self._media)

            def setup(_opaque, chroma, width, height, pitches, lines):
                width_value = int(width[0])
                height_value = int(height[0])
                self._buffer.configure(width_value, height_value)
                ctypes.memmove(chroma, self.pixel_format.encode("ascii"), 4)
                for index, value in enumerate(self._buffer.pitches):
                    pitches[index] = value
                for index, value in enumerate(self._buffer.lines):
                    lines[index] = value
                return self._buffer.BUFFER_COUNT

            def cleanup(_opaque):
                self._buffer.cleanup_retired()

            def lock(_opaque, planes):
                token, pointers = self._buffer.acquire_planes()
                for index, pointer in enumerate(pointers):
                    planes[index] = pointer
                return token

            def unlock(_opaque, picture, _planes):
                # Legacy decoders do not reliably call display for every
                # locked picture. Release the pool slot as soon as VLC has
                # finished writing it so decoder threads can never deadlock.
                token = (
                    int(picture)
                    if isinstance(picture, int)
                    else int(getattr(picture, "value", 0) or 0)
                )
                self._buffer.publish(token)

            def display(_opaque, _picture):
                return None

            def playback_error(_event):
                self._playback_error.set()

            setup_cb = self._decorate("VideoFormatCb", setup)
            cleanup_cb = self._decorate("VideoCleanupCb", cleanup)
            lock_cb = self._decorate("VideoLockCb", lock)
            unlock_cb = self._decorate("VideoUnlockCb", unlock)
            display_cb = self._decorate("VideoDisplayCb", display)
            # EventManager.event_attach owns the generic event callback wrapper.
            # Decorating it again breaks the callback arity on playback errors.
            event_cb = playback_error
            self._callbacks = [
                setup_cb, cleanup_cb, lock_cb, unlock_cb, display_cb, event_cb
            ]

            self._player.video_set_callbacks(
                lock_cb, unlock_cb, display_cb, ctypes.c_void_p()
            )
            self._player.video_set_format_callbacks(setup_cb, cleanup_cb)
            event_manager = self._player.event_manager()
            event_manager.event_attach(
                self._vlc.EventType.MediaPlayerEncounteredError, event_cb
            )
            self._opened = self._player.play() != -1
        except Exception:
            self.release()
            raise

    def isOpened(self) -> bool:
        return self._opened and not self._released

    def read(self):
        if not self.isOpened() or self._playback_error.is_set():
            return False, None
        frame = self._buffer.read(self.frame_timeout)
        return (frame is not None), frame

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._buffer.width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._buffer.height
        if prop == cv2.CAP_PROP_FPS:
            return 0.0
        return 0

    @property
    def dropped_frames(self) -> int:
        return self._buffer.dropped_frames

    @property
    def buffer_pressure(self) -> int:
        with self._buffer._condition:
            return len(self._buffer._active_tokens)

    def set(self, _prop, _value) -> bool:
        return False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._opened = False
        player, media, instance = self._player, self._media, self._instance
        self._player = self._media = self._instance = None
        if player is not None:
            try:
                # Keep callback storage alive until VLC has stopped all decoder
                # threads. Closing the buffer first can make a final lock
                # callback return null planes and crash inside native VLC.
                player.stop()
            finally:
                player.release()
        self._buffer.close()
        if media is not None:
            media.release()
        if instance is not None:
            instance.release()


class VLCLocalBridgeCapture:
    """Let VLC normalize legacy RTSP into a localhost MPEG-TS stream.

    Video is remuxed, not transcoded. OpenCV performs the only decode, avoiding
    libVLC's multi-process display-callback deadlock on legacy DVR streams.
    """

    _active_processes: set[subprocess.Popen] = set()

    def __init__(
        self,
        url: str,
        frame_timeout_seconds: float,
        network_caching_ms: int = 200,
        rtsp_tcp: bool = False,
        vlc_binary: str | None = None,
    ) -> None:
        self.url = url
        self.frame_timeout = frame_timeout_seconds
        self._process: subprocess.Popen | None = None
        self._capture = None
        self._released = False
        self._dropped_frames = 0
        self._media_anchor_ms: float | None = None
        self._wall_anchor: float | None = None
        self._last_media_ms: float | None = None
        binary = vlc_binary or os.getenv("CITYEYE_VLC_BINARY") or self._find_vlc()
        if not binary:
            raise RuntimeError("Headless VLC executable was not found")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.local_url = f"http://127.0.0.1:{port}/camera.ts"
        command = [
            binary, "-I", "dummy", "--no-audio", "--no-video-title-show",
            "--http-host=127.0.0.1", url,
            f":network-caching={int(network_caching_ms)}",
        ]
        if rtsp_tcp:
            command.append(":rtsp-tcp")
        command.extend([
            "--sout",
            f"#standard{{access=http,mux=ts,dst=127.0.0.1:{port}/camera.ts}}",
            "--sout-keep",
        ])
        self._process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # Keep VLC in the worker's process group so launchd shutdowns do
            # not leave DVR sessions and localhost listeners orphaned.
            start_new_session=False,
        )
        self._active_processes.add(self._process)
        deadline = time.monotonic() + max(5.0, frame_timeout_seconds)
        listener_ready = False
        while time.monotonic() < deadline and self._process.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    listener_ready = True
                    break
            except OSError:
                time.sleep(0.1)
        if listener_ready and self._process.poll() is None:
            try:
                self._capture = cv2.VideoCapture(
                    self.local_url,
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        int(frame_timeout_seconds * 1000),
                    ],
                )
            except (TypeError, cv2.error):
                self._capture = cv2.VideoCapture(self.local_url)
            if not self._capture.isOpened():
                self._capture.release()
                self._capture = None
            else:
                self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    @staticmethod
    def _find_vlc() -> str | None:
        candidates = [
            shutil.which("cvlc"),
            shutil.which("vlc"),
            "/Applications/VLC.app/Contents/MacOS/VLC",
        ]
        return next((path for path in candidates if path and Path(path).is_file()), None)

    def isOpened(self) -> bool:
        return bool(
            not self._released and self._capture is not None
            and self._capture.isOpened() and self._process is not None
            and self._process.poll() is None
        )

    def read(self):
        if not self.isOpened():
            return False, None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return ok, frame
        media_ms = float(self._capture.get(cv2.CAP_PROP_POS_MSEC))
        self._pace_media_frame(media_ms)
        return ok, frame

    def _pace_media_frame(self, media_ms: float) -> None:
        """Restore MPEG-TS presentation pacing lost by the localhost remux.

        The legacy DVR often delivers several valid frames in a burst. OpenCV
        drains them immediately even though their PTS values are ~80 ms apart,
        which makes motion alternate between jumps and pauses. We sleep only
        to honor real media timestamps; no frame is fabricated or replayed.
        """
        if media_ms <= 0:
            return
        now = time.monotonic()
        if (
            self._media_anchor_ms is None
            or self._wall_anchor is None
            or (self._last_media_ms is not None and media_ms <= self._last_media_ms)
        ):
            self._media_anchor_ms = media_ms
            self._wall_anchor = now
            self._last_media_ms = media_ms
            return
        target = self._wall_anchor + (media_ms - self._media_anchor_ms) / 1000.0
        lag = now - target
        # Never play a stale backlog after a network/DVR pause. Re-anchor at
        # the current live edge; RTSPFrameSource handles genuinely stale reads.
        if lag > 0.5:
            self._media_anchor_ms = media_ms
            self._wall_anchor = now
        elif target > now:
            time.sleep(min(target - now, 0.25))
        self._last_media_ms = media_ms

    def get(self, prop):
        return self._capture.get(prop) if self._capture is not None else 0

    def set(self, prop, value) -> bool:
        return bool(self._capture is not None and self._capture.set(prop, value))

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    @property
    def buffer_pressure(self) -> int:
        return 0

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process is not None:
            self._active_processes.discard(process)
        self._process = None

    @classmethod
    def shutdown_all(cls) -> None:
        """Best-effort cleanup for bridges interrupted during construction."""
        for process in tuple(cls._active_processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            cls._active_processes.discard(process)


class RTSPFrameSource:
    """Latest-frame RTSP reader with bounded backoff and stale-stream recovery."""

    def __init__(
        self,
        camera_id: str,
        url: str,
        reconnect_enabled: bool = True,
        reconnect_delay_seconds: float = 2.0,
        max_reconnect_delay_seconds: float = 16.0,
        stale_after_seconds: float = 5.0,
        connect_timeout_seconds: float = 10.0,
        capture_backend: CaptureBackend = CaptureBackend.OPENCV,
        vlc_network_caching_ms: int = 200,
        vlc_rtsp_tcp: bool = False,
        capture_factory: Callable = cv2.VideoCapture,
        vlc_capture_factory: Callable | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        status_callback: Callable[[CameraHealth], None] | None = None,
        frame_callback: Callable[[np.ndarray, float, int], bool] | None = None,
        visual_difference_threshold: float = 0.08,
        visual_stale_after_seconds: float = 15.0,
        visual_minimum_similar_frames: int = 30,
        visual_changes_to_arm: int = 3,
    ) -> None:
        if not camera_id.strip():
            raise ValueError("camera_id must not be empty")
        if reconnect_delay_seconds <= 0 or max_reconnect_delay_seconds <= 0:
            raise ValueError("reconnect delays must be positive")
        if max_reconnect_delay_seconds < reconnect_delay_seconds:
            raise ValueError("max reconnect delay must not be smaller than initial delay")
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")
        self.camera_id = camera_id
        self.url = url
        self.reconnect_enabled = reconnect_enabled
        self.initial_delay = reconnect_delay_seconds
        self.max_delay = max_reconnect_delay_seconds
        self.stale_after = stale_after_seconds
        self.connect_timeout = connect_timeout_seconds
        self.capture_backend = parse_capture_backend(capture_backend)
        self.vlc_network_caching_ms = int(vlc_network_caching_ms)
        self.vlc_rtsp_tcp = bool(vlc_rtsp_tcp)
        if self.vlc_network_caching_ms < 0:
            raise ValueError("vlc_network_caching_ms must not be negative")
        self.capture_factory = capture_factory
        self.vlc_capture_factory = vlc_capture_factory or (
            VLCLocalBridgeCapture if sys.platform == "darwin" else VLCFrameCapture
        )
        self.clock = clock
        self.sleep = sleep
        self.status_callback = status_callback
        self.frame_callback = frame_callback
        self.health = CameraHealth(camera_id, SourceType.RTSP)
        self.width = self.height = self.total_frames = 0
        self.fps = 0.0
        self._condition = threading.Condition()
        self._latest: FramePacket | None = None
        self._sequence = 0
        self._consumed_sequence = 0
        self._generation = 0
        self._capture_times: deque[float] = deque()
        self._preview_times: deque[float] = deque()
        self._last_health_publish_at = 0.0
        self._freshness_options = {
            "difference_threshold": visual_difference_threshold,
            "stale_after_seconds": visual_stale_after_seconds,
            "minimum_similar_frames": visual_minimum_similar_frames,
            "changes_to_arm": visual_changes_to_arm,
            "clock": clock,
        }
        self._freshness = VisualFreshnessTracker(**self._freshness_options)
        self._stopped = threading.Event()
        self._capture = None
        self._worker = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def _publish_health(self) -> None:
        if self.status_callback:
            self.status_callback(self.health)

    def _set_state(self, state: CameraState, error: str | None = None) -> None:
        self.health.state = state
        self.health.last_error = error
        if state is not CameraState.ONLINE:
            self.health.processing_fps = 0.0
            self.health.ai_inference_fps = 0.0
        self._publish_health()

    def _open_opencv(self):
        if self.capture_factory is cv2.VideoCapture:
            try:
                capture = self.capture_factory(
                    self.url,
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        int(self.connect_timeout * 1000),
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        int(self.stale_after * 1000),
                    ],
                )
            except (TypeError, cv2.error):
                # Older OpenCV builds do not accept constructor parameters.
                capture = self.capture_factory(self.url)
        else:
            capture = self.capture_factory(self.url)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not capture.isOpened():
            capture.release()
            return None
        return capture

    def _open_vlc(self):
        try:
            capture = self.vlc_capture_factory(
                self.url,
                frame_timeout_seconds=self.stale_after,
                network_caching_ms=self.vlc_network_caching_ms,
                rtsp_tcp=self.vlc_rtsp_tcp,
            )
        except (ImportError, OSError, RuntimeError) as exc:
            self.health.last_error = f"VLC capture unavailable: {exc}"
            return None
        if not capture.isOpened():
            capture.release()
            return None
        return capture

    def _open(self):
        if self.capture_backend is CaptureBackend.OPENCV:
            capture = self._open_opencv()
        elif self.capture_backend is CaptureBackend.VLC:
            capture = self._open_vlc()
        else:
            capture = self._open_opencv()
            if capture is None:
                capture = self._open_vlc()
        if capture is None:
            return None
        self.width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = float(capture.get(cv2.CAP_PROP_FPS))
        return capture

    def _run(self) -> None:
        delay = self.initial_delay
        while not self._stopped.is_set():
            self._set_state(CameraState.RECONNECTING, self.health.last_error)
            self._capture = self._open()
            if self._capture is None:
                self.health.reconnect_attempts += 1
                self._set_state(CameraState.OFFLINE, "RTSP connection failed")
                if not self.reconnect_enabled:
                    break
                self._set_state(CameraState.RECONNECTING, "RTSP connection failed")
                self._wait_before_reconnect(delay)
                delay = min(self.max_delay, delay * 2)
                continue

            delay = self.initial_delay
            self._freshness = VisualFreshnessTracker(**self._freshness_options)
            self._capture_times.clear()
            self._preview_times.clear()
            while not self._stopped.is_set():
                started = self.clock()
                ok, frame = self._capture.read()
                finished = self.clock()
                if not ok or frame is None:
                    self._set_state(CameraState.RECONNECTING, "RTSP stream lost")
                    break
                self.height, self.width = frame.shape[:2]
                self._freshness.observe(frame, finished)
                self._capture_times.append(finished)
                while self._capture_times and finished - self._capture_times[0] > 5.0:
                    self._capture_times.popleft()
                capture_span = (
                    self._capture_times[-1] - self._capture_times[0]
                    if len(self._capture_times) > 1 else 0.0
                )
                self.health.heartbeat_at = finished
                self.health.callback_sequence = self._freshness.callback_sequence
                self.health.visual_sequence = self._freshness.visual_sequence
                self.health.last_visual_change_at = self._freshness.last_visual_change_at
                self.health.consecutive_similar_frames = (
                    self._freshness.consecutive_similar_frames
                )
                self.health.camera_capture_fps = (
                    (len(self._capture_times) - 1) / capture_span
                    if capture_span > 0 else 0.0
                )
                self.health.dropped_frames = int(
                    getattr(self._capture, "dropped_frames", 0)
                )
                self.health.buffer_pressure = int(
                    getattr(self._capture, "buffer_pressure", 0)
                )
                if self.frame_callback and self.frame_callback(
                    frame, finished, self._sequence
                ):
                    self._preview_times.append(finished)
                    while self._preview_times and finished - self._preview_times[0] > 5.0:
                        self._preview_times.popleft()
                    preview_span = (
                        self._preview_times[-1] - self._preview_times[0]
                        if len(self._preview_times) > 1 else 0.0
                    )
                    self.health.preview_publication_fps = (
                        (len(self._preview_times) - 1) / preview_span
                        if preview_span > 0 else 0.0
                    )
                    self.health.preview_last_frame_at = finished
                # Keep status independent from the slower inference consumer.
                if finished - self._last_health_publish_at >= 1.0:
                    self._last_health_publish_at = finished
                    self._publish_health()
                if self._freshness.is_stuck(finished):
                    self._set_state(
                        CameraState.STALE,
                        "Decoded callbacks continued but source pixels stopped changing",
                    )
                    break
                if finished - started > self.stale_after:
                    self._set_state(
                        CameraState.RECONNECTING,
                        "RTSP frame read became stale",
                    )
                    break
                if self.health.state is not CameraState.ONLINE:
                    self._generation += 1
                    self.health.generation = self._generation
                    self.health.last_connected_at = finished
                    self._set_state(CameraState.ONLINE)
                with self._condition:
                    packet = FramePacket(frame, self._sequence, finished, self._generation)
                    self._sequence += 1
                    self._latest = packet
                    self.health.last_frame_at = finished
                    self.health.state = CameraState.ONLINE
                    self.health.last_error = None
                    self._condition.notify_all()

            self._capture.release()
            self._capture = None
            if self._stopped.is_set() or not self.reconnect_enabled:
                break
            self.health.reconnect_attempts += 1
            self._set_state(CameraState.RECONNECTING, self.health.last_error)
            self._wait_before_reconnect(delay)
            delay = min(self.max_delay, delay * 2)

        self._set_state(CameraState.OFFLINE, self.health.last_error)
        with self._condition:
            self._condition.notify_all()

    def _wait_before_reconnect(self, delay: float) -> None:
        if self.sleep is time.sleep:
            self._stopped.wait(delay)
        else:
            self.sleep(delay)

    def read(self, timeout: float | None = 1.0) -> FramePacket | None:
        self.start()
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while (
                not self._stopped.is_set()
                and self._sequence <= self._consumed_sequence
            ):
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if self._latest is None or self._sequence <= self._consumed_sequence:
                return None
            self._consumed_sequence = self._sequence
            return self._latest

    def close(self) -> None:
        self._stopped.set()
        with self._condition:
            self._condition.notify_all()
        if self._worker.is_alive():
            # The reader thread owns VideoCapture. Releasing it concurrently
            # with a native read can crash some OpenCV/FFmpeg builds.
            self._worker.join(timeout=self.stale_after + 1.0)


def reconnect_delays(initial: float, maximum: float, attempts: int) -> list[float]:
    """Expose deterministic backoff calculation for tests and documentation."""
    if initial <= 0 or maximum < initial or attempts < 0:
        raise ValueError("invalid reconnect backoff configuration")
    return [min(maximum, initial * (2**index)) for index in range(attempts)]
