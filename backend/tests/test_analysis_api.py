from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app


def make_client(tmp_path: Path, output_dir: Path) -> TestClient:
    return TestClient(create_app(
        database_path=tmp_path / "analysis.db",
        evidence_dir=tmp_path / "evidence",
        ai_output_dir=output_dir,
    ))


def test_summary_counts_distinct_ids_in_last_frame(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "tracks.csv").write_text(
        "frame,track_id,class_name\n10,1,car\n10,2,bus\n11,2,bus\n11,3,truck\n11,,car\n",
        encoding="utf-8",
    )
    with make_client(tmp_path, output_dir) as client:
        response = client.get("/api/analysis/summary")
    assert response.status_code == 200
    assert response.json() == {
        "status": "READY", "current_vehicle_count": 3, "last_frame": 11,
        "total_track_records": 5, "annotated_video_available": False,
        "message": "Summary calculated from the real tracks.csv output.",
    }


def test_summary_reports_missing_outputs_honestly(tmp_path: Path) -> None:
    with make_client(tmp_path, tmp_path / "missing") as client:
        payload = client.get("/api/analysis/summary").json()
    assert payload["status"] == "MISSING"
    assert payload["current_vehicle_count"] is None
    assert payload["annotated_video_available"] is False


def test_summary_handles_valid_csv_with_no_detections(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "tracks.csv").write_text("frame,track_id,class_name\n", encoding="utf-8")
    with make_client(tmp_path, output_dir) as client:
        payload = client.get("/api/analysis/summary").json()
    assert payload["status"] == "READY"
    assert payload["current_vehicle_count"] == 0
    assert payload["last_frame"] is None


def test_summary_reports_invalid_csv(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "tracks.csv").write_text("wrong,column\n1,2\n", encoding="utf-8")
    with make_client(tmp_path, output_dir) as client:
        payload = client.get("/api/analysis/summary").json()
    assert payload["status"] == "INVALID"
    assert payload["current_vehicle_count"] is None


def test_serves_only_fixed_annotated_mp4(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    video_bytes = b"cityeye-test-mp4"
    (output_dir / "annotated.mp4").write_bytes(video_bytes)
    with make_client(tmp_path, output_dir) as client:
        response = client.get("/media/annotated.mp4")
    assert response.status_code == 200
    assert response.content == video_bytes
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["cache-control"] == "no-store"


def test_missing_annotated_video_returns_404(tmp_path: Path) -> None:
    with make_client(tmp_path, tmp_path / "output") as client:
        response = client.get("/media/annotated.mp4")
    assert response.status_code == 404


def test_rejects_annotated_video_symlink_outside_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"private")
    (output_dir / "annotated.mp4").symlink_to(outside)
    with make_client(tmp_path, output_dir) as client:
        response = client.get("/media/annotated.mp4")
    assert response.status_code == 404
