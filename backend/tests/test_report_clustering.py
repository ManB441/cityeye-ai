from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import CitizenReportRepository, haversine_distance_meters
from app.schemas import CitizenReportCreate, ReportStatus


BASE_LATITUDE = 31.95
BASE_LONGITUDE = 35.91


def make_report(
    demo_user_id: str,
    category: str = "CONGESTION",
    latitude: float = BASE_LATITUDE,
    longitude: float = BASE_LONGITUDE,
) -> CitizenReportCreate:
    return CitizenReportCreate.model_validate(
        {
            "category": category,
            "description": "Compatible demo traffic report.",
            "latitude": latitude,
            "longitude": longitude,
            "demo_user_id": demo_user_id,
        }
    )


def make_repository(
    tmp_path: Path,
    timestamps: list[float],
    count: int,
) -> CitizenReportRepository:
    time_values = iter(timestamps)
    id_values = iter(f"report-{index}" for index in range(1, count + 1))
    repository = CitizenReportRepository(
        tmp_path / "clustering.db",
        clock=lambda: next(time_values),
        id_factory=lambda: next(id_values),
    )
    repository.initialize()
    return repository


def test_haversine_distance_is_zero_for_same_point() -> None:
    assert haversine_distance_meters(
        BASE_LATITUDE,
        BASE_LONGITUDE,
        BASE_LATITUDE,
        BASE_LONGITUDE,
    ) == pytest.approx(0.0)


def test_fifth_distinct_user_confirms_compatible_cluster(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 240], 5)

    reports = [
        repository.add(make_report(f"demo-user-{index}"))
        for index in range(1, 6)
    ]

    assert [report.status for report in reports[:4]] == [ReportStatus.PENDING] * 4
    assert reports[4].status is ReportStatus.COMMUNITY_CONFIRMED
    assert {report.status for report in repository.list()} == {
        ReportStatus.COMMUNITY_CONFIRMED
    }


def test_repeated_reports_from_same_user_count_once(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 240, 300], 6)
    users = ["user-1", "user-1", "user-2", "user-3", "user-4", "user-4"]

    reports = [repository.add(make_report(user)) for user in users]

    assert {report.status for report in reports} == {ReportStatus.PENDING}


def test_report_beyond_100_meters_does_not_join_cluster(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 240], 5)
    for index in range(1, 5):
        repository.add(make_report(f"user-{index}"))

    far_report = repository.add(
        make_report("user-5", latitude=BASE_LATITUDE + 0.002)
    )

    assert haversine_distance_meters(
        BASE_LATITUDE,
        BASE_LONGITUDE,
        far_report.latitude,
        far_report.longitude,
    ) > 100
    assert {report.status for report in repository.list()} == {ReportStatus.PENDING}


def test_report_with_different_category_does_not_join_cluster(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 240], 5)
    for index in range(1, 5):
        repository.add(make_report(f"user-{index}"))

    different = repository.add(make_report("user-5", category="ROAD_HAZARD"))

    assert different.status is ReportStatus.PENDING
    assert {report.status for report in repository.list()} == {ReportStatus.PENDING}


def test_report_older_than_15_minutes_does_not_join_cluster(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 901], 5)
    for index in range(1, 5):
        repository.add(make_report(f"user-{index}"))

    fifth = repository.add(make_report("user-5"))

    assert fifth.status is ReportStatus.PENDING
    assert {report.status for report in repository.list()} == {ReportStatus.PENDING}


def test_report_exactly_at_time_boundary_is_compatible(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 100, 200, 300, 900], 5)

    for index in range(1, 6):
        final_report = repository.add(make_report(f"user-{index}"))

    assert final_report.status is ReportStatus.COMMUNITY_CONFIRMED


def test_nearby_sixth_user_joins_existing_confirmed_cluster(tmp_path: Path) -> None:
    repository = make_repository(tmp_path, [0, 60, 120, 180, 240, 300], 6)
    for index in range(1, 6):
        repository.add(make_report(f"user-{index}"))

    sixth = repository.add(make_report("user-6"))

    assert sixth.status is ReportStatus.COMMUNITY_CONFIRMED
    assert len(repository.list()) == 6


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_distinct_users": 1},
        {"cluster_radius_meters": 0},
        {"cluster_window_seconds": 0},
    ],
)
def test_rejects_invalid_cluster_configuration(
    tmp_path: Path,
    overrides: dict,
) -> None:
    with pytest.raises(ValueError):
        CitizenReportRepository(tmp_path / "invalid.db", **overrides)
