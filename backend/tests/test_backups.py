from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.backups import check_latest_backup, create_backup, list_backups, restore_backup


def _create_database(path: Path, value: str = "original") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE settings (value TEXT NOT NULL)")
        connection.execute("INSERT INTO settings VALUES (?)", (value,))


def _read_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM settings").fetchone()[0]


def test_backup_and_restore_preserve_database_content(tmp_path: Path) -> None:
    database = tmp_path / "cityeye.db"
    backup_dir = tmp_path / "backups"
    _create_database(database)

    backup = create_backup(database, backup_dir)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE settings SET value = 'changed'")

    restore_backup(Path(backup.name), database, backup_dir)

    assert _read_value(database) == "original"
    assert backup.with_suffix(".json").is_file()


def test_retention_keeps_only_newest_backups(tmp_path: Path) -> None:
    database = tmp_path / "cityeye.db"
    backup_dir = tmp_path / "backups"
    _create_database(database)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for offset in range(4):
        create_backup(
            database,
            backup_dir,
            retention_count=2,
            now=start + timedelta(minutes=offset),
        )

    backups = list_backups(backup_dir)
    assert len(backups) == 2
    assert "000300" in backups[0].name
    assert "000200" in backups[1].name
    assert len(list(backup_dir.glob("*.json"))) == 2


def test_restore_rejects_checksum_mismatch(tmp_path: Path) -> None:
    database = tmp_path / "cityeye.db"
    backup_dir = tmp_path / "backups"
    _create_database(database)
    backup = create_backup(database, backup_dir)
    backup.write_bytes(backup.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_backup(Path(backup.name), database, backup_dir)


def test_restore_rejects_path_outside_backup_directory(tmp_path: Path) -> None:
    database = tmp_path / "cityeye.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    with pytest.raises(ValueError, match="inside CITYEYE_BACKUP_DIR"):
        restore_backup(Path("../cityeye-stolen.sqlite3"), database, backup_dir)


def test_backup_requires_existing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Database not found"):
        create_backup(tmp_path / "missing.db", tmp_path / "backups")


def test_latest_backup_health_verifies_recent_backup(tmp_path: Path) -> None:
    database = tmp_path / "cityeye.db"
    backup_dir = tmp_path / "backups"
    _create_database(database)
    backup = create_backup(database, backup_dir)

    assert check_latest_backup(backup_dir, max_age_seconds=60) == backup


def test_latest_backup_health_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No database backups found"):
        check_latest_backup(tmp_path / "backups", max_age_seconds=60)
