"""The smoke entry point must never target an external service or inherited DB."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke_test.py"


def test_smoke_has_no_external_target_arguments():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--backend" not in result.stdout
    assert "--frontend" not in result.stdout


def test_smoke_ignores_inherited_operational_paths(tmp_path):
    database = tmp_path / "operational.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('unchanged')")
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                            env={**os.environ, "CITYEYE_DATABASE_PATH": str(database),
                                 "CITYEYE_ENVIRONMENT": "production",
                                 "CITYEYE_LIVE_OUTPUT_DIR": str(tmp_path / "must-not-create")}, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ISOLATED SYNTHETIC SMOKE: PASS" in result.stdout
    assert "restore" in result.stdout.lower()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not (tmp_path / "must-not-create").exists()


def test_missing_recorded_assets_fail_with_instructions(tmp_path):
    import json
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"video_source": "missing.mp4", "model": "missing.pt"}))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check-recorded-inputs.py"),
                             "--config", str(config), "--ai-root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Missing video" in result.stderr
    assert "Missing model weights" in result.stderr
    assert "no download was attempted" in result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_recorded_preflight_rejects_replaced_source(tmp_path):
    import json
    (tmp_path / "video.mp4").write_bytes(b"synthetic source")
    (tmp_path / "model.pt").write_bytes(b"synthetic model placeholder")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"video_source": "video.mp4", "model": "model.pt",
                                 "recorded_calibration": {"source_sha256": "0" * 64}}))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check-recorded-inputs.py"),
                             "--config", str(config), "--ai-root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "SHA-256 does not match" in result.stderr
