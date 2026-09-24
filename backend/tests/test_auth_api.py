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
    assert "access_token" not in response.json()
    token = client.cookies.get("cityeye_session")
    assert token
    return token


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
        repository.create_user("reviewer", "reviewer-password-123", "EMPLOYEE")
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
        repository.create_user("operator", "operator-password-123", "CITIZEN")
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
                "role": "EMPLOYEE",
            },
            headers=headers,
        )
        users = client.get("/api/users", headers=headers)
        duplicate = client.post(
            "/api/users",
            json={
                "username": "municipal-reviewer",
                "password": "another-password-123",
                "role": "CITIZEN",
            },
            headers=headers,
        )
        audit = client.get("/api/audit", headers=headers)

    assert created.status_code == 201
    assert created.json()["role"] == "EMPLOYEE"
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
        repository.create_user("reviewer", "reviewer-password-123", "EMPLOYEE")
        token = login(client, "reviewer", "reviewer-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/users", headers=headers).status_code == 403
        assert client.post(
            "/api/users",
            json={
                "username": "operator",
                "password": "operator-password-123",
                "role": "CITIZEN",
            },
            headers=headers,
        ).status_code == 403


def test_sensitive_endpoints_require_credentials(monkeypatch, tmp_path: Path) -> None:
    configure_required_auth(monkeypatch, tmp_path)
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        assert client.post("/api/events/missing/verify").status_code == 401
        assert client.post("/api/events/ingest", json=event_payload()).status_code == 401
        assert client.get("/api/events").status_code == 401


def test_auth_required_fails_closed_without_users(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CITYEYE_AUTH_REQUIRED", "true")
    monkeypatch.delenv("CITYEYE_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("CITYEYE_INGEST_TOKEN_FILE", str(tmp_path / "missing"))
    application = create_app(database_path=tmp_path / "cityeye.db")

    with pytest.raises(RuntimeError, match="no users exist"):
        with TestClient(application):
            pass


@pytest.mark.parametrize("path", [
    "/api/events", "/api/users", "/api/audit", "/api/live-cameras",
    "/api/live-cameras/camera-3/metrics", "/api/analytics/traffic",
    "/api/scenarios", "/media/annotated.mp4", "/media/live-cameras/camera-3.mjpg",
    "/evidence/example.jpg",
])
def test_all_product_surfaces_are_private(monkeypatch, tmp_path, path):
    configure_required_auth(monkeypatch, tmp_path)
    with TestClient(create_app(database_path=tmp_path / "cityeye.db")) as client:
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Request-ID"]


def test_cookie_security_expiry_and_revocation(monkeypatch, tmp_path):
    configure_required_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("CITYEYE_ENVIRONMENT", "production")
    monkeypatch.setenv("CITYEYE_TRUSTED_HOSTS", "cityeye.example.gov")
    monkeypatch.setenv("CITYEYE_CORS_ORIGINS", "https://cityeye.example.gov")
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database), base_url="https://cityeye.example.gov") as client:
        response = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        cookie = response.headers["set-cookie"]
        assert all(value in cookie for value in ("HttpOnly", "Secure", "SameSite=strict", "Max-Age=28800"))
        assert response.headers["Cache-Control"] == "no-store"
        token = client.cookies.get("cityeye_session")
        assert client.get("/api/events").status_code == 200
        with sqlite3.connect(database) as connection:
            stored = connection.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
            assert stored != token and len(stored) == 64
            connection.execute("UPDATE auth_sessions SET expires_at = 0")
        assert client.get("/api/events").status_code == 401
        assert client.get("/api/auth/session").json()["user"] is None
        fresh = login(client, "admin", ADMIN_PASSWORD)
        assert fresh != token
        assert client.post("/api/auth/logout").status_code == 200
        assert not client.cookies.get("cityeye_session")
        assert client.get("/api/events", headers={"Authorization": f"Bearer {fresh}"}).status_code == 401


@pytest.mark.parametrize("role", ["ADMIN", "EMPLOYEE", "CITIZEN"])
@pytest.mark.parametrize("prefix", ["/api/events", "/api/live-camera/events", "/api/live-cameras/camera-3/events", "/api/scenarios/normal_traffic/events"])
@pytest.mark.parametrize("decision", ["verify", "dismiss"])
def test_review_permissions_on_every_source(monkeypatch, tmp_path, role, prefix, decision):
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database)) as client:
        AuthRepository(database).create_user("role-test", "test-password-long", role)
        login(client, "role-test", "test-password-long")
        response = client.post(f"{prefix}/not-an-event/{decision}")
        assert response.status_code == (403 if role == "CITIZEN" else 404)


def test_access_updates_revoke_sessions_and_protect_last_admin(monkeypatch, tmp_path):
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database)) as client:
        admin_token = login(client, "admin", ADMIN_PASSWORD)
        admin = client.get("/api/auth/session").json()["user"]
        assert client.patch(f'/api/users/{admin["user_id"]}', json={"active": False}).status_code == 409
        assert client.patch(f'/api/users/{admin["user_id"]}', json={"role": "CITIZEN"}).status_code == 409
        created = client.post("/api/users", json={"username": "reviewer", "password": "long-password-test", "role": "EMPLOYEE"}).json()
        reviewer_token = login(client, "reviewer", "long-password-test")
        assert client.patch(f'/api/users/{created["user_id"]}', json={"role": "ADMIN"}).status_code == 403
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.patch(f'/api/users/{created["user_id"]}', headers=headers, json={"active": False}).status_code == 200
        assert client.get("/api/events", headers={"Authorization": f"Bearer {reviewer_token}"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "reviewer", "password": "long-password-test"}).status_code == 401


def test_cross_origin_writes_rejected_and_preflight_supported(monkeypatch, tmp_path):
    configure_required_auth(monkeypatch, tmp_path)
    with TestClient(create_app(database_path=tmp_path / "cityeye.db")) as client:
        credentials = {"username": "admin", "password": ADMIN_PASSWORD}
        assert client.post("/api/auth/login", json=credentials, headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post("/api/auth/login", json=credentials, headers={"Origin": "http://testserver"}).status_code == 200
        assert client.post("/api/auth/logout", headers={"Origin": "https://other.example"}).status_code == 403
        response = client.options("/api/users", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH"})
        assert response.status_code == 200


def test_production_cannot_disable_auth(monkeypatch):
    from app.auth import AuthSettings
    monkeypatch.setenv("CITYEYE_AUTH_REQUIRED", "false")
    with pytest.raises(ValueError, match="Production requires"):
        AuthSettings.from_environment("production")


def citizen_payload(identity="forged"):
    return {"category": "CONGESTION", "description": "Traffic is slow",
            "latitude": 31.95, "longitude": 35.91, "demo_user_id": identity}


def test_reports_require_live_session(monkeypatch, tmp_path):
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database)) as client:
        assert client.post("/api/citizen-reports", json=citizen_payload()).status_code == 401
        login(client, "admin", ADMIN_PASSWORD)
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE auth_sessions SET expires_at = 0")
        assert client.post("/api/citizen-reports", json=citizen_payload()).status_code == 401
        token = login(client, "admin", ADMIN_PASSWORD)
        client.post("/api/auth/logout")
        assert client.post("/api/citizen-reports", json=citizen_payload(),
                           headers={"Authorization": f"Bearer {token}"}).status_code == 401
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM citizen_reports").fetchone()[0] == 0


def test_report_consensus_uses_distinct_authenticated_accounts(monkeypatch, tmp_path):
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database)) as client:
        repository = AuthRepository(database)
        users = [repository.create_user(f"citizen-{i}", "citizen-password-test", "CITIZEN") for i in range(5)]
        login(client, users[0].username, "citizen-password-test")
        for i in range(6):
            result = client.post("/api/citizen-reports", json=citizen_payload(f"forged-{i}"))
            assert result.status_code == 201
            assert result.json()["demo_user_id"] == users[0].user_id
            assert result.json()["status"] == "PENDING"
        for i, user in enumerate(users[1:], 1):
            login(client, user.username, "citizen-password-test")
            result = client.post("/api/citizen-reports", json=citizen_payload())
            assert result.status_code == 201
            assert result.json()["demo_user_id"] == user.user_id
            assert result.json()["status"] == ("COMMUNITY_CONFIRMED" if i == 4 else "PENDING")
        assert {r["status"] for r in client.get("/api/citizen-reports").json()["reports"]} == {"COMMUNITY_CONFIRMED"}


@pytest.mark.parametrize("role", ["ADMIN", "EMPLOYEE", "CITIZEN"])
def test_role_access_matrix(monkeypatch, tmp_path, role):
    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    with TestClient(create_app(database_path=database)) as client:
        user = AuthRepository(database).create_user("matrix", "matrix-password-test", role)
        login(client, "matrix", "matrix-password-test")
        assert client.get("/api/citizen-reports").status_code == 200
        assert client.post("/api/citizen-reports", json=citizen_payload()).status_code == 201
        for path in ["/api/events", "/api/scenarios", "/api/live-cameras", "/api/audit"]:
            assert client.get(path).status_code == (403 if role == "CITIZEN" else 200)
        assert client.get("/api/users").status_code == (200 if role == "ADMIN" else 403)
        assert client.patch(f"/api/users/{user.user_id}", json={"active": False}).status_code == (200 if role == "ADMIN" else 403)


def test_legacy_reports_do_not_vote_in_authenticated_consensus(monkeypatch, tmp_path):
    from app.database import CitizenReportRepository
    from app.schemas import CitizenReportCreate

    configure_required_auth(monkeypatch, tmp_path)
    database = tmp_path / "cityeye.db"
    repository = CitizenReportRepository(database)
    repository.initialize()
    for i in range(4):
        repository.add(CitizenReportCreate(**citizen_payload(f"legacy-{i}")))
    # Recreate the pre-upgrade schema to exercise the additive migration.
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE citizen_reports DROP COLUMN authenticated_user_id")
    with TestClient(create_app(database_path=database)) as client:
        login(client, "admin", ADMIN_PASSWORD)
        response = client.post("/api/citizen-reports", json=citizen_payload())
        assert response.status_code == 201
        assert response.json()["status"] == "PENDING"
        assert client.get("/api/citizen-reports").json()["total"] == 5
        # Demo fixtures added after authentication must not count real users either.
        added = repository.add(CitizenReportCreate(**citizen_payload("legacy-4")))
        assert added.status == "COMMUNITY_CONFIRMED"
        assert client.get(f'/api/citizen-reports/{response.json()["report_id"]}').json()["status"] == "PENDING"
    repository.initialize()  # Migration remains safe on subsequent startup.
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM citizen_reports WHERE authenticated_user_id IS NOT NULL").fetchone()[0] == 1
