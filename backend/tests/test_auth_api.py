from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import AuthRepository
from app.main import create_app


ADMIN_PASSWORD = "correct-horse-battery-staple"
INGEST_TOKEN = "ingest-token-with-enough-entropy-for-tests"


def configure_required_auth(monkeypatch, tmp_path: Path) -> None:
    admin_secret = tmp_path / "admin_password"
    ingest_secret = tmp_path / "ingest_token"
    admin_secret.write_text(ADMIN_PASSWORD, encoding="utf-8")
    ingest_secret.write_text(INGEST_TOKEN, encoding="utf-8")
    monkeypatch.setenv("CITYEYE_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CITYEYE_BOOTSTRAP_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(admin_secret))
    monkeypatch.setenv("CITYEYE_INGEST_TOKEN_FILE", str(ingest_secret))


def event_payload() -> dict[str, object]:
    return {
        "event_id": "auth-event-1",
        "event_type": "WRONG_WAY",
        "timestamp": 10.0,
        "confidence": 0.91,
        "severity": "HIGH",
        "explanation": "Track moved opposite to traffic.",
        "camera_name": "Camera 1",
        "latitude": 31.95,
        "longitude": 35.91,
        "evidence_image": "evidence/auth-event-1.jpg",
        "status": "PROPOSED",
    }


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_session_logout_and_hashed_token(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    application = create_app(database_path=database)

    with TestClient(application) as client:
        token = login(client, "admin", ADMIN_PASSWORD)
        session = client.get(
            "/api/auth/session", headers={"Authorization": f"Bearer {token}"}
        )
        assert session.json()["user"]["role"] == "ADMIN"
        assert client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 200
        assert client.get(
            "/api/auth/session", headers={"Authorization": f"Bearer {token}"}
        ).json()["user"] is None

    with sqlite3.connect(database) as connection:
        stored_tokens = [row[0] for row in connection.execute("SELECT token_hash FROM auth_sessions")]
    assert token not in stored_tokens


def test_invalid_login_uses_generic_error(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "wrong"}
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_reviewer_can_decide_and_audit_records_actor(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    application = create_app(database_path=database)

    with TestClient(application) as client:
        repository = AuthRepository(database)
        repository.create_user("reviewer", "reviewer-password-123", "REVIEWER")
        reviewer_token = login(client, "reviewer", "reviewer-password-123")
        admin_token = login(client, "admin", ADMIN_PASSWORD)
        assert client.post(
            "/api/events/ingest",
            json=event_payload(),
            headers={"X-CityEye-Ingest-Token": INGEST_TOKEN},
        ).status_code == 201

        reviewed = client.post(
            "/api/events/auth-event-1/verify",
            headers={
                "Authorization": f"Bearer {reviewer_token}",
                "X-Request-ID": "review-request-1",
            },
        )
        audit = client.get(
            "/api/audit", headers={"Authorization": f"Bearer {admin_token}"}
        )

    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "VERIFIED"
    assert audit.status_code == 200
    assert audit.json()["entries"][0]["actor_username"] == "reviewer"
    assert audit.json()["entries"][0]["previous_value"] == "PROPOSED"
    assert audit.json()["entries"][0]["new_value"] == "VERIFIED"
    assert audit.json()["entries"][0]["request_id"] == "review-request-1"


def test_operator_cannot_review_or_read_audit(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    application = create_app(database_path=database)

    with TestClient(application) as client:
        repository = AuthRepository(database)
        repository.create_user("operator", "operator-password-123", "OPERATOR")
        token = login(client, "operator", "operator-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/events/missing/verify", headers=headers).status_code == 403
        assert client.get("/api/audit", headers=headers).status_code == 403


def test_admin_can_create_and_list_users(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        admin_token = login(client, "admin", ADMIN_PASSWORD)
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "X-Request-ID": "create-user-request",
        }
        created = client.post(
            "/api/users",
            json={
                "username": "municipal-reviewer",
                "password": "reviewer-password-123",
                "role": "REVIEWER",
            },
            headers=headers,
        )
        users = client.get("/api/users", headers=headers)
        duplicate = client.post(
            "/api/users",
            json={
                "username": "municipal-reviewer",
                "password": "another-password-123",
                "role": "OPERATOR",
            },
            headers=headers,
        )
        audit = client.get("/api/audit", headers=headers)

    assert created.status_code == 201
    assert created.json()["role"] == "REVIEWER"
    assert users.status_code == 200
    assert {user["username"] for user in users.json()["users"]} == {
        "admin",
        "municipal-reviewer",
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Username already exists"
    assert audit.json()["entries"][0]["action"] == "USER_CREATED"
    assert audit.json()["entries"][0]["request_id"] == "create-user-request"


def test_non_admin_cannot_manage_users(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    application = create_app(database_path=database)

    with TestClient(application) as client:
        repository = AuthRepository(database)
        repository.create_user("reviewer", "reviewer-password-123", "REVIEWER")
        token = login(client, "reviewer", "reviewer-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/users", headers=headers).status_code == 403
        assert client.post(
            "/api/users",
            json={
                "username": "operator",
                "password": "operator-password-123",
                "role": "OPERATOR",
            },
            headers=headers,
        ).status_code == 403


def test_sensitive_endpoints_require_credentials(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        assert client.post("/api/events/missing/verify").status_code == 401
        assert client.post("/api/events/ingest", json=event_payload()).status_code == 401
        assert client.get("/api/events").status_code == 200


def test_auth_required_fails_closed_without_users(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CITYEYE_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CITYEYE_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("CITYEYE_INGEST_TOKEN_FILE", str(tmp_path / "missing"))
    application = create_app(database_path=tmp_path / "cityeye.db")

    with pytest.raises(RuntimeError, match="no users exist"):
        with TestClient(application):
            pass
