#!/usr/bin/env python3
"""Run SYNTHETIC API and backup checks in a disposable in-process application.

No external URL or database destination is accepted. This does not validate
YOLO, camera behavior, real stopped events, Docker networking or video playback.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_environment(root: Path):
    # Clear inherited production configuration before importing the application.
    saved = {key: value for key, value in os.environ.items() if key.startswith("CITYEYE_")}
    for key in saved:
        del os.environ[key]
    password = secrets.token_urlsafe(24)
    ingest = secrets.token_urlsafe(24)
    for name, value in (("password", password), ("ingest", ingest)):
        path = root / name
        path.write_text(value)
        path.chmod(0o600)
    os.environ.update({
        "CITYEYE_ENVIRONMENT": "development", "CITYEYE_AUTH_REQUIRED": "true",
        "CITYEYE_DATABASE_PATH": str(root / "smoke.db"),
        "CITYEYE_EVIDENCE_DIR": str(root / "evidence"),
        "CITYEYE_AI_OUTPUT_DIR": str(root / "ai"),
        "CITYEYE_SCENARIO_OUTPUT_ROOT": str(root / "scenarios"),
        "CITYEYE_LIVE_OUTPUT_DIR": str(root / "live"),
        "CITYEYE_BOOTSTRAP_ADMIN_USERNAME": "smoke-admin",
        "CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE": str(root / "password"),
        "CITYEYE_INGEST_TOKEN_FILE": str(root / "ingest"),
    })
    try:
        yield password, ingest
    finally:
        for key in list(os.environ):
            if key.startswith("CITYEYE_"):
                del os.environ[key]
        os.environ.update(saved)


def check(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(label)
    print(f"PASS  {label}")


def run(root: Path, password: str, ingest: str) -> None:
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.backups import create_backup, restore_backup, verify_backup

    database = root / "smoke.db"
    def login(client, username):
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        check(response.status_code == 200, f"login {username}")
        return client.cookies.get("cityeye_session")

    with TestClient(create_app()) as client:
        check(client.get("/health/ready").status_code == 200, "isolated database readiness")
        check(client.get("/api/events").status_code == 401, "anonymous access denied")
        admin = login(client, "smoke-admin")
        for role in ("EMPLOYEE", "CITIZEN"):
            response = client.post("/api/users", json={"username": role, "password": password, "role": role})
            check(response.status_code == 201, f"create {role} fixture account")
        # Explicit synthetic proposal: no inference or real-camera claim.
        proposal = {"event_id": "synthetic-smoke-event", "event_type": "STOPPED_VEHICLE",
                    "timestamp": 100, "confidence": .9, "severity": "MEDIUM",
                    "explanation": "SYNTHETIC API fixture; no real vehicle observation",
                    "camera_name": "Synthetic fixture", "latitude": 0, "longitude": 0,
                    "evidence_image": "fixture.jpg", "source_type": "LIVE_CAMERA", "source_id": "camera-3"}
        response = client.post("/api/events/ingest", json=proposal, headers={"X-CityEye-Ingest-Token": ingest})
        check(response.status_code == 201, "synthetic proposal persisted")
        login(client, "CITIZEN")
        check(client.post("/api/events/synthetic-smoke-event/verify").status_code == 403, "citizen cannot review")
        check(client.get("/api/users").status_code == 403, "citizen cannot administer users")
        login(client, "EMPLOYEE")
        check(client.get("/api/users").status_code == 403, "employee cannot administer users")
        response = client.post("/api/events/synthetic-smoke-event/verify")
        check(response.status_code == 200 and response.json()["status"] == "VERIFIED", "employee verifies fixture")
        response = client.post("/api/events/synthetic-smoke-event/dismiss", headers={"Authorization": f"Bearer {admin}"})
        check(response.status_code == 200 and response.json()["status"] == "DISMISSED", "admin dismisses fixture")
        token = client.cookies.get("cityeye_session")
        check(client.post("/api/auth/logout").status_code == 200, "logout")
        check(client.get("/api/events", headers={"Authorization": f"Bearer {token}"}).status_code == 401, "revoked session rejected")

    # Close all app workers before backup; restore only into a NEW temporary DB.
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    backup_dir = root / "backups"
    backup = create_backup(database, backup_dir)
    verify_backup(backup)
    restored = root / "restored.db"
    restore_backup(backup, restored, backup_dir)
    with sqlite3.connect(database) as source, sqlite3.connect(restored) as destination:
        check(destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "restored database integrity")
        check(list(source.iterdump()) == list(destination.iterdump()), "restore preserves complete schema and data")
    check(hashlib.sha256(database.read_bytes()).hexdigest() == before, "backup/restore leaves source database unchanged")
    with TestClient(create_app(database_path=restored)) as client:
        login(client, "smoke-admin")
        response = client.get("/api/events/synthetic-smoke-event")
        check(response.status_code == 200 and response.json()["status"] == "DISMISSED", "restored review survives application restart")
        check(len(client.get("/api/audit").json()["entries"]) >= 4, "restored audit history")
    print("ISOLATED SYNTHETIC SMOKE: PASS (temporary files removed on exit)")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        with TemporaryDirectory(prefix="cityeye-smoke-") as directory:
            root = Path(directory)
            with isolated_environment(root) as (password, ingest):
                run(root, password, ingest)
    except ImportError as exc:
        print(f"SMOKE: FAIL — missing dependency {exc.name}; install backend/requirements.txt into backend/.venv", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"SMOKE: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
