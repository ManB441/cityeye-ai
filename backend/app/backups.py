"""Verified SQLite backup, retention, and recovery utilities."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import time
from typing import Sequence


DEFAULT_DATABASE_PATH = Path(os.getenv("CITYEYE_DATABASE_PATH", "/data/cityeye.db"))
DEFAULT_BACKUP_DIR = Path(os.getenv("CITYEYE_BACKUP_DIR", "/backups"))
DEFAULT_RETENTION_COUNT = int(os.getenv("CITYEYE_BACKUP_RETENTION_COUNT", "14"))
DEFAULT_INTERVAL_SECONDS = int(os.getenv("CITYEYE_BACKUP_INTERVAL_SECONDS", "86400"))
DEFAULT_MAX_AGE_SECONDS = int(
    os.getenv("CITYEYE_BACKUP_MAX_AGE_SECONDS", str(DEFAULT_INTERVAL_SECONDS * 2))
)
BACKUP_PREFIX = "cityeye-"
BACKUP_SUFFIX = ".sqlite3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_database(path: Path) -> None:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise ValueError(f"Invalid SQLite database: {path.name}") from exc
    if result is None or result[0] != "ok":
        raise ValueError(f"SQLite integrity check failed for {path.name}: {result}")


def list_backups(backup_dir: Path) -> list[Path]:
    """Return managed backups newest first."""
    if not backup_dir.exists():
        return []
    return sorted(
        backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"),
        key=lambda path: path.name,
        reverse=True,
    )


def prune_backups(backup_dir: Path, retention_count: int) -> list[Path]:
    """Delete managed backups beyond the configured count."""
    if retention_count < 1:
        raise ValueError("retention_count must be at least 1")
    removed: list[Path] = []
    for backup_path in list_backups(backup_dir)[retention_count:]:
        backup_path.unlink()
        backup_path.with_suffix(".json").unlink(missing_ok=True)
        removed.append(backup_path)
    return removed


def verify_backup(backup_path: Path) -> None:
    """Verify a managed backup against its manifest and SQLite integrity."""
    manifest_path = backup_path.with_suffix(".json")
    if not manifest_path.is_file():
        raise ValueError(f"Backup manifest not found: {manifest_path.name}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid backup manifest: {manifest_path.name}") from exc
    if manifest.get("filename") != backup_path.name:
        raise ValueError(f"Backup manifest filename mismatch: {backup_path.name}")
    if manifest.get("sha256") != _sha256(backup_path):
        raise ValueError(f"Backup checksum mismatch: {backup_path.name}")
    _verify_database(backup_path)


def check_latest_backup(backup_dir: Path, max_age_seconds: int) -> Path:
    """Return the latest verified backup or fail when it is stale."""
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be positive")
    backups = list_backups(backup_dir)
    if not backups:
        raise ValueError("No database backups found")
    latest = backups[0]
    verify_backup(latest)
    age_seconds = time.time() - latest.stat().st_mtime
    if age_seconds > max_age_seconds:
        raise ValueError(
            f"Latest database backup is stale: {round(age_seconds)} seconds old"
        )
    return latest


def create_backup(
    database_path: Path,
    backup_dir: Path,
    retention_count: int = DEFAULT_RETENTION_COUNT,
    now: datetime | None = None,
) -> Path:
    """Create, verify, and atomically publish an online SQLite backup."""
    if not database_path.is_file():
        raise FileNotFoundError(f"Database not found: {database_path}")
    if retention_count < 1:
        raise ValueError("retention_count must be at least 1")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    filename = f"{BACKUP_PREFIX}{timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}{BACKUP_SUFFIX}"
    final_path = backup_dir / filename
    temporary_path = backup_dir / f".{filename}.tmp"

    try:
        with sqlite3.connect(database_path, timeout=10.0) as source:
            with sqlite3.connect(temporary_path) as destination:
                source.backup(destination)
        _verify_database(temporary_path)
        os.replace(temporary_path, final_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    manifest = {
        "filename": final_path.name,
        "created_at": timestamp.isoformat(),
        "size_bytes": final_path.stat().st_size,
        "sha256": _sha256(final_path),
    }
    final_path.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    prune_backups(backup_dir, retention_count)
    return final_path


def restore_backup(backup_path: Path, database_path: Path, backup_dir: Path) -> Path:
    """Verify and atomically restore one managed backup."""
    backup_root = backup_dir.resolve()
    selected = backup_path if backup_path.is_absolute() else backup_root / backup_path
    selected = selected.resolve()
    if selected.parent != backup_root or not selected.name.startswith(BACKUP_PREFIX):
        raise ValueError("Backup must be a managed file inside CITYEYE_BACKUP_DIR")
    if not selected.is_file() or selected.suffix != BACKUP_SUFFIX:
        raise FileNotFoundError(f"Backup not found: {selected.name}")

    verify_backup(selected)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = database_path.parent / f".{database_path.name}.restore.tmp"
    try:
        with sqlite3.connect(f"file:{selected}?mode=ro", uri=True) as source:
            with sqlite3.connect(temporary_path) as destination:
                source.backup(destination)
        _verify_database(temporary_path)
        os.replace(temporary_path, database_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return database_path


def run_worker(database_path: Path, backup_dir: Path, retention_count: int, interval_seconds: int) -> None:
    """Create backups on an interval until Docker requests shutdown."""
    if interval_seconds < 60:
        raise ValueError("interval_seconds must be at least 60")
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        backup = create_backup(database_path, backup_dir, retention_count)
        print(json.dumps({"event": "database_backup_created", "path": backup.name}), flush=True)
        deadline = time.monotonic() + interval_seconds
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("backup", "check", "list", "restore", "worker")
    )
    parser.add_argument("backup", nargs="?", help="Backup filename for restore")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--retention-count", type=int, default=DEFAULT_RETENTION_COUNT)
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "backup":
        print(create_backup(args.database, args.backup_dir, args.retention_count))
    elif args.action == "check":
        print(check_latest_backup(args.backup_dir, args.max_age_seconds))
    elif args.action == "list":
        for path in list_backups(args.backup_dir):
            print(path.name)
    elif args.action == "restore":
        if not args.backup:
            raise SystemExit("restore requires a backup filename")
        print(restore_backup(Path(args.backup), args.database, args.backup_dir))
    else:
        run_worker(args.database, args.backup_dir, args.retention_count, args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
