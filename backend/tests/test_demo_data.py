from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import CitizenReportRepository
from app.demo_data import DEMO_USER_PREFIX, main, reset_demo_reports, seed_demo_reports
from app.schemas import CitizenReportCreate, ReportStatus


def test_seed_creates_confirmed_five_user_cluster(tmp_path: Path) -> None:
    database_path = tmp_path / "demo.db"
    created = seed_demo_reports(database_path)
    reports = CitizenReportRepository(database_path).list()

    assert len(created) == 5
    assert len(reports) == 5
    assert {report.status for report in reports} == {
        ReportStatus.COMMUNITY_CONFIRMED
    }
    assert len({report.demo_user_id for report in reports}) == 5
    assert all(report.demo_user_id.startswith(DEMO_USER_PREFIX) for report in reports)


def test_seed_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "demo.db"
    assert len(seed_demo_reports(database_path)) == 5
    assert seed_demo_reports(database_path) == []
    assert len(CitizenReportRepository(database_path).list()) == 5


def test_reset_deletes_only_command_owned_demo_reports(tmp_path: Path) -> None:
    database_path = tmp_path / "demo.db"
    seed_demo_reports(database_path)
    repository = CitizenReportRepository(database_path)
    repository.add(
        CitizenReportCreate(
            category="ROAD_HAZARD",
            description="A non-demo report that must remain.",
            latitude=31.95,
            longitude=35.91,
            demo_user_id="student-test-user",
        )
    )

    assert reset_demo_reports(database_path) == 5
    remaining = repository.list()
    assert len(remaining) == 1
    assert remaining[0].demo_user_id == "student-test-user"


def test_reset_is_safe_when_no_demo_reports_exist(tmp_path: Path) -> None:
    assert reset_demo_reports(tmp_path / "demo.db") == 0


def test_cli_seed_and_reset_use_selected_database(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "selected.db"
    assert main(["seed", "--database", str(database_path)]) == 0
    assert "Created 5 demo Citizen Reports" in capsys.readouterr().out
    assert main(["reset", "--database", str(database_path)]) == 0
    assert "Deleted 5 demo Citizen Reports" in capsys.readouterr().out
