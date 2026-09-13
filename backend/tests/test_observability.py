import json
import logging
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.observability import JsonFormatter, artifact_health, database_health


def test_json_formatter_emits_operational_fields() -> None:
    record = logging.LogRecord(
        "cityeye.backend", logging.INFO, __file__, 1, "request_completed", (), None
    )
    record.request_id = "request-1"
    record.status_code = 200

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "request_completed"
    assert payload["request_id"] == "request-1"
    assert payload["status_code"] == 200
    assert payload["timestamp"].endswith("+00:00")


def test_database_health_reports_failure_when_parent_is_a_file(tmp_path: Path) -> None:
    invalid_parent = tmp_path / "not-a-directory"
    invalid_parent.write_text("occupied", encoding="utf-8")

    result = database_health(invalid_parent / "cityeye.db")

    assert result["status"] == "failed"
    assert result["detail"]


def test_artifact_health_reports_ready_when_required_files_exist(tmp_path: Path) -> None:
    (tmp_path / "tracks.csv").touch()
    (tmp_path / "annotated.mp4").touch()

    assert artifact_health(tmp_path) == {"status": "ok"}
