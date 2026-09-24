"""Retryable ingestion of mounted AI artifacts into the existing incident domain."""
from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath
import re
import threading

from app.database import EventRepository
from app.schemas import TrafficEventIngest

LOGGER = logging.getLogger(__name__)
SOURCE_ID = re.compile(r"[A-Za-z0-9_-]+")


class LiveIncidentImporter:
    """Files are delivery artifacts; SQLite is the authoritative incident history."""

    def __init__(self, root: Path, repository: EventRepository) -> None:
        self.root = root.resolve()
        self.repository = repository
        self._completed: dict[str, tuple[int, int, int]] = {}
        self._lock = threading.Lock()

    def sync(self, camera_id: str) -> None:
        with self._lock:
            self._sync(camera_id)

    def _sync(self, camera_id: str) -> None:
        if not SOURCE_ID.fullmatch(camera_id):
            raise ValueError("Invalid live incident source ID")
        directory = (self.root / camera_id).resolve()
        if directory.parent != self.root:
            raise ValueError("Live incident source escapes its configured root")
        path = directory / "events.json"
        if not path.exists():
            return
        stat = path.stat()
        fingerprint = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if self._completed.get(camera_id) == fingerprint:
            return
        payloads = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payloads, list):
            raise ValueError("Live events must be a JSON list")
        complete = True
        for payload in payloads:
            try:
                event = TrafficEventIngest.model_validate({
                    **payload, "status": "PROPOSED",
                    "source_type": "LIVE_CAMERA", "source_id": camera_id,
                })
                reference = PurePosixPath(event.evidence_image)
                if "\\" in event.evidence_image or reference.parts not in {
                    (reference.name,), ("evidence", reference.name),
                }:
                    raise ValueError("Invalid live evidence reference")
                evidence_root = directory / "evidence"
                evidence = (evidence_root / reference.name).resolve()
                if evidence.parent != evidence_root or not evidence.is_file():
                    raise ValueError("Live evidence is not available inside its source")
                # An interrupted image write is retried; no broken proposal is published.
                data = evidence.read_bytes()
                if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                    raise ValueError("Live evidence JPG is incomplete")
                self.repository.ingest_once(event)
            except Exception:
                complete = False
                LOGGER.exception("Could not ingest a live incident for %s; will retry", camera_id)
        if complete:
            self._completed[camera_id] = fingerprint

    def sync_safely(self, camera_id: str) -> None:
        try:
            self.sync(camera_id)
        except Exception:
            LOGGER.exception("Could not read live incidents for %s; will retry", camera_id)
