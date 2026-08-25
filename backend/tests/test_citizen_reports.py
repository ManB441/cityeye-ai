from pathlib import Path
import sqlite3
import sys

import pytest
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import CitizenReportRepository
from app.schemas import (
    CitizenReportCreate,
    ReportCategory,
    ReportStatus,
)


def valid_report_payload() -> dict:
    return {
        "category": "CONGESTION",
        "description": "Traffic is moving very slowly.",
        "latitude": 31.95,
        "longitude": 35.91,
        "demo_user_id": "demo-user-1",
    }


def make_report(**overrides: object) -> CitizenReportCreate:
    payload = valid_report_payload()
    payload.update(overrides)
    return CitizenReportCreate.model_validate(payload)


@pytest.fixture
def repository(tmp_path: Path) -> CitizenReportRepository:
    repo = CitizenReportRepository(
        tmp_path / "citizen_reports.db",
        clock=lambda: 1_700_000_000.0,
        id_factory=lambda: "report-fixed-id",
    )
    repo.initialize()
    return repo


def test_accepts_and_normalizes_citizen_report_input() -> None:
    report = make_report(
        description="  Slow traffic near the bridge.  ",
        demo_user_id="  demo-user-1  ",
    )

    assert report.category is ReportCategory.CONGESTION
    assert report.description == "Slow traffic near the bridge."
    assert report.demo_user_id == "demo-user-1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "UNKNOWN"),
        ("description", "  "),
        ("description", " x "),
        ("description", "x" * 501),
        ("latitude", 91),
        ("longitude", -181),
        ("demo_user_id", ""),
        ("demo_user_id", "x" * 65),
    ],
)
def test_rejects_invalid_citizen_report_input(field: str, value: object) -> None:
    payload = valid_report_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        CitizenReportCreate.model_validate(payload)


def test_rejects_unknown_report_fields() -> None:
    payload = valid_report_payload()
    payload["user_name"] = "Private Name"

    with pytest.raises(ValidationError):
        CitizenReportCreate.model_validate(payload)


def test_initialize_creates_citizen_reports_table(
    repository: CitizenReportRepository,
) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'citizen_reports'
            """
        ).fetchone()

    assert table == ("citizen_reports",)


def test_initialize_is_idempotent(repository: CitizenReportRepository) -> None:
    repository.initialize()
    repository.initialize()

    assert repository.list() == []


def test_add_generates_server_fields_and_pending_status(
    repository: CitizenReportRepository,
) -> None:
    stored = repository.add(make_report())

    assert stored.report_id == "report-fixed-id"
    assert stored.reported_at == 1_700_000_000.0
    assert stored.status is ReportStatus.PENDING
    assert repository.get(stored.report_id) == stored


def test_get_missing_report_returns_none(
    repository: CitizenReportRepository,
) -> None:
    assert repository.get("missing") is None


def test_list_returns_newest_report_first(tmp_path: Path) -> None:
    timestamps = iter([100.0, 200.0])
    identifiers = iter(["older", "newer"])
    repository = CitizenReportRepository(
        tmp_path / "ordered_reports.db",
        clock=lambda: next(timestamps),
        id_factory=lambda: next(identifiers),
    )
    repository.initialize()
    repository.add(make_report(demo_user_id="demo-user-1"))
    repository.add(make_report(demo_user_id="demo-user-2"))

    reports = repository.list()

    assert [report.report_id for report in reports] == ["newer", "older"]


def test_reports_can_share_category_without_early_confirmation(tmp_path: Path) -> None:
    identifiers = iter(["report-1", "report-2"])
    repository = CitizenReportRepository(
        tmp_path / "pending_reports.db",
        clock=lambda: 100.0,
        id_factory=lambda: next(identifiers),
    )
    repository.initialize()
    first = repository.add(make_report(demo_user_id="demo-user-1"))
    second = repository.add(make_report(demo_user_id="demo-user-2"))

    assert first.status is ReportStatus.PENDING
    assert second.status is ReportStatus.PENDING
