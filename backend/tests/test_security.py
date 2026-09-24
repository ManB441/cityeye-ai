from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.security import SECURITY_HEADERS, SecuritySettings


def test_responses_include_security_headers(tmp_path: Path) -> None:
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_cors_allows_only_configured_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CITYEYE_CORS_ORIGINS", "https://dashboard.example.gov")
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        allowed = client.options(
            "/api/events",
            headers={
                "Origin": "https://dashboard.example.gov",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = client.options(
            "/api/events",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://dashboard.example.gov"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_invalid_external_request_id_is_replaced(tmp_path: Path) -> None:
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "bad id"})

    assert response.headers["X-Request-ID"] != "bad id"
    assert " " not in response.headers["X-Request-ID"]


def test_production_disables_api_docs(monkeypatch, tmp_path: Path) -> None:
    from test_auth_api import configure_required_auth
    configure_required_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("CITYEYE_ENVIRONMENT", "production")
    monkeypatch.setenv("CITYEYE_TRUSTED_HOSTS", "cityeye.example.gov")
    monkeypatch.setenv("CITYEYE_CORS_ORIGINS", "https://cityeye.example.gov")
    application = create_app(database_path=tmp_path / "cityeye.db")

    with TestClient(application, base_url="https://cityeye.example.gov") as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("CITYEYE_TRUSTED_HOSTS", "*", "explicit CITYEYE_TRUSTED_HOSTS"),
        ("CITYEYE_CORS_ORIGINS", "*", "cannot contain a wildcard"),
        (
            "CITYEYE_CORS_ORIGINS",
            "http://cityeye.example.gov",
            "must use HTTPS",
        ),
    ],
)
def test_production_rejects_unsafe_configuration(
    monkeypatch, variable: str, value: str, message: str
) -> None:
    monkeypatch.setenv("CITYEYE_ENVIRONMENT", "production")
    monkeypatch.setenv("CITYEYE_TRUSTED_HOSTS", "cityeye.example.gov")
    monkeypatch.setenv("CITYEYE_CORS_ORIGINS", "https://cityeye.example.gov")
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=message):
        SecuritySettings.from_environment()


def test_production_rejects_placeholder_host(monkeypatch) -> None:
    monkeypatch.setenv("CITYEYE_ENVIRONMENT", "production")
    monkeypatch.setenv("CITYEYE_TRUSTED_HOSTS", "CHANGE-ME.example.gov")
    monkeypatch.setenv("CITYEYE_CORS_ORIGINS", "https://cityeye.example.gov")

    with pytest.raises(ValueError, match="Replace CHANGE-ME"):
        SecuritySettings.from_environment()
