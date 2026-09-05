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
        scenario_output_root=tmp_path / "scenarios",
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
        "status": "READY", "current_vehicle_count": 3,
        "current_people_count": 0, "last_frame": 11,
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


def test_timeline_returns_real_per_frame_class_counts(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "tracks.csv").write_text(
        "frame,timestamp_sec,track_id,class_name\n"
        "10,1.0,1,car\n10,1.0,2,truck\n10,1.0,2,truck\n"
        "11,1.1,1,car\n11,1.1,3,bus\n11,1.1,,motorcycle\n",
        encoding="utf-8",
    )
    with make_client(tmp_path, output_dir) as client:
        response = client.get("/api/analysis/timeline")
    assert response.status_code == 200
    assert response.json() == {
        "status": "READY",
        "frames": [
            {"frame": 10, "timestamp_sec": 1.0, "active_vehicle_count": 2,
                 "cars": 1, "buses": 0, "trucks": 1, "motorcycles": 0,
                 "people": 0, "people_in_road": 0, "tracked_people": 0},
            {"frame": 11, "timestamp_sec": 1.1, "active_vehicle_count": 3,
                 "cars": 1, "buses": 1, "trucks": 0, "motorcycles": 1,
                 "people": 0, "people_in_road": 0, "tracked_people": 0},
        ],
        "message": "Timeline calculated from real YOLO and ByteTrack output.",
    }


def test_people_are_reported_without_increasing_vehicle_count(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "tracks.csv").write_text(
        "frame,timestamp_sec,track_id,class_name,person_in_road\n"
        "1,0.1,1,car,\n1,0.1,2,person,True\n1,0.1,,person,False\n",
        encoding="utf-8",
    )

    with make_client(tmp_path, output_dir) as client:
        summary = client.get("/api/analysis/summary").json()
        frame = client.get("/api/analysis/timeline").json()["frames"][0]

    assert summary["current_vehicle_count"] == 1
    assert summary["current_people_count"] == 2
    assert frame["active_vehicle_count"] == 1
    assert frame["people"] == 2
    assert frame["people_in_road"] == 1
    assert frame["tracked_people"] == 1


def test_timeline_reports_missing_tracks_honestly(tmp_path: Path) -> None:
    with make_client(tmp_path, tmp_path / "missing") as client:
        payload = client.get("/api/analysis/timeline").json()
    assert payload["status"] == "MISSING"
    assert payload["frames"] == []


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


def test_scenario_endpoints_use_only_allowlisted_real_outputs(tmp_path: Path) -> None:
    scenario = tmp_path / "scenarios" / "congestion"
    (scenario / "evidence").mkdir(parents=True)
    (scenario / "tracks.csv").write_text(
        "frame,timestamp_sec,track_id,class_name\n1,0.1,1,car\n", encoding="utf-8"
    )
    (scenario / "annotated.mp4").write_bytes(b"h264-video")
    (scenario / "evidence" / "event.jpg").write_bytes(b"jpg")
    (scenario / "events.json").write_text(
        '[{"event_id":"real-1","event_type":"CONGESTION","timestamp":0.1,'
        '"confidence":0.8,"severity":"MEDIUM","explanation":"Real tracked congestion",'
        '"camera_name":"Test camera","latitude":0,"longitude":0,'
        '"evidence_image":"evidence/event.jpg","status":"PROPOSED"}]', encoding="utf-8"
    )
    with make_client(tmp_path, tmp_path / "output") as client:
        scenarios = client.get("/api/scenarios")
        assert scenarios.status_code == 200
        assert "rainy_traffic" in {
            item["scenario_id"] for item in scenarios.json()["scenarios"]
        }
        assert client.get("/api/scenarios/congestion/analysis/timeline").json()["frames"][0]["cars"] == 1
        assert client.get("/api/scenarios/congestion/events").json()["total"] == 1
        assert client.get("/media/scenarios/congestion/annotated.mp4").content == b"h264-video"
        assert client.get("/evidence/scenarios/congestion/event.jpg").status_code == 200
        reviewed = client.post("/api/scenarios/congestion/events/real-1/verify")
        assert reviewed.json()["status"] == "VERIFIED"
        assert client.get("/api/scenarios/../../private/analysis/summary").status_code in {404, 405}


def test_rejects_annotated_video_symlink_outside_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"private")
    (output_dir / "annotated.mp4").symlink_to(outside)
    with make_client(tmp_path, output_dir) as client:
        response = client.get("/media/annotated.mp4")
    assert response.status_code == 404
