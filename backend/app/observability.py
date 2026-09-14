"""Runtime logging and health helpers for the CityEye backend."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import re
from typing import Any


SENSITIVE_PATTERNS = (
    re.compile(r"(rtsp://[^:/\s]+:)[^@/\s]+(@)", re.IGNORECASE),
    re.compile(
        r"((?:password|passwd|token|api[_-]?key|secret)[\s=:]+)[^\s,;]+",
        re.IGNORECASE,
    ),
)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def redact_sensitive(value: str) -> str:
    """Remove common credentials from text before it reaches logs."""
    redacted = value
    redacted = SENSITIVE_PATTERNS[0].sub(r"\1***\2", redacted)
    redacted = SENSITIVE_PATTERNS[1].sub(r"\1***", redacted)
    return redacted


def safe_request_id(value: str | None) -> str | None:
    """Accept only bounded, header-safe request identifiers."""
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return None


class JsonFormatter(logging.Formatter):
    """Emit one machine-readable JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive(record.getMessage()),
        }
        for field in (
            "environment",
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = redact_sensitive(
                self.formatException(record.exc_info)
            )
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging() -> logging.Logger:
    """Configure application logs once and return the service logger."""
    level_name = os.getenv("CITYEYE_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("cityeye.backend")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def database_health(database_path: Path) -> dict[str, str]:
    """Verify that SQLite can be opened and queried."""
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path, timeout=2.0) as connection:
            connection.execute("SELECT 1").fetchone()
    except (OSError, sqlite3.Error) as exc:
        return {"status": "failed", "detail": str(exc)}
    return {"status": "ok"}


def artifact_health(output_dir: Path) -> dict[str, str]:
    """Report AI artifact availability without making it a hard dependency."""
    required = ("tracks.csv", "annotated.mp4")
    missing = [name for name in required if not (output_dir / name).is_file()]
    if missing:
        return {
            "status": "degraded",
            "detail": f"Optional AI artifacts missing: {', '.join(missing)}",
        }
    return {"status": "ok"}
