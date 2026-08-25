from pathlib import Path
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app, resolve_evidence_path


JPEG_BYTES = b"\xff\xd8\xff\xe0cityeye-test\xff\xd9"


@pytest.fixture
def evidence_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "evidence"
    directory.mkdir()
    return directory


@pytest.fixture
def client(tmp_path: Path, evidence_dir: Path):
    application = create_app(
        database_path=tmp_path / "evidence_api.db",
        evidence_dir=evidence_dir,
    )
    with TestClient(application) as test_client:
        yield test_client


@pytest.mark.parametrize("filename", ["event_0001.jpg", "event_0002.JPEG"])
def test_serves_existing_jpg_evidence(
    client: TestClient,
    evidence_dir: Path,
    filename: str,
) -> None:
    (evidence_dir / filename).write_bytes(JPEG_BYTES)

    response = client.get(f"/evidence/{filename}")

    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_missing_evidence_returns_404(client: TestClient) -> None:
    response = client.get("/evidence/missing.jpg")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence image not found: missing.jpg"


@pytest.mark.parametrize("filename", ["event.png", "event.mp4", "event", "bad\\name.jpg"])
def test_rejects_non_jpg_or_unsafe_filename(
    evidence_dir: Path,
    filename: str,
) -> None:
    with pytest.raises(HTTPException) as error:
        resolve_evidence_path(evidence_dir, filename)

    assert error.value.status_code == 400


@pytest.mark.parametrize("filename", ["../secret.jpg", "folder/event.jpg", "/tmp/event.jpg"])
def test_rejects_path_traversal(evidence_dir: Path, filename: str) -> None:
    with pytest.raises(HTTPException) as error:
        resolve_evidence_path(evidence_dir, filename)

    assert error.value.status_code == 400


def test_rejects_symlink_that_escapes_evidence_directory(
    evidence_dir: Path,
    tmp_path: Path,
) -> None:
    outside_file = tmp_path / "outside.jpg"
    outside_file.write_bytes(JPEG_BYTES)
    link = evidence_dir / "linked.jpg"
    link.symlink_to(outside_file)

    with pytest.raises(HTTPException) as error:
        resolve_evidence_path(evidence_dir, link.name)

    assert error.value.status_code == 400


def test_openapi_lists_evidence_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/evidence/{filename}" in paths
