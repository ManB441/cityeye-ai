"""Seed and reset clearly labeled local demo Citizen Reports."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
from typing import Sequence

from app.database import CitizenReportRepository
from app.schemas import CitizenReportCreate, CitizenReportResponse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "cityeye.db"
DEMO_USER_PREFIX = "cityeye-demo-user-"


def seed_demo_reports(database_path: Path) -> list[CitizenReportResponse]:
    """Create five compatible reports through the real clustering logic."""
    repository = CitizenReportRepository(database_path)
    repository.initialize()
    existing_demo_users = {
        report.demo_user_id
        for report in repository.list()
        if report.demo_user_id.startswith(DEMO_USER_PREFIX)
    }
    reports: list[CitizenReportResponse] = []
    coordinates = (
        (31.95390, 35.91060),
        (31.95396, 35.91064),
        (31.95384, 35.91057),
        (31.95392, 35.91051),
        (31.95387, 35.91068),
    )
    for index, (latitude, longitude) in enumerate(coordinates, start=1):
        demo_user_id = f"{DEMO_USER_PREFIX}{index}"
        if demo_user_id in existing_demo_users:
            continue
        reports.append(
            repository.add(
                CitizenReportCreate(
                    category="CONGESTION",
                    description="Demo fixture report for the competition map.",
                    latitude=latitude,
                    longitude=longitude,
                    demo_user_id=demo_user_id,
                )
            )
        )
    return reports


def reset_demo_reports(database_path: Path) -> int:
    """Delete only reports created by this demo-data command."""
    repository = CitizenReportRepository(database_path)
    repository.initialize()
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM citizen_reports WHERE demo_user_id LIKE ?",
            (f"{DEMO_USER_PREFIX}%",),
        )
        return cursor.rowcount


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage local CityEye AI demo Citizen Reports."
    )
    parser.add_argument("command", choices=("seed", "reset"))
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("CITYEYE_DATABASE_PATH", DEFAULT_DATABASE_PATH)),
        help="SQLite path (defaults to CITYEYE_DATABASE_PATH or backend/data/cityeye.db).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        created = seed_demo_reports(args.database)
        print(f"Created {len(created)} demo Citizen Reports in {args.database}")
        print("Demo fixtures are clearly labeled and are not AI-generated events.")
    else:
        deleted = reset_demo_reports(args.database)
        print(f"Deleted {deleted} demo Citizen Reports from {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
