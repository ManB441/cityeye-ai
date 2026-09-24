"""Background collectors must never import the developer's real camera artifacts."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_live_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("CITYEYE_LIVE_OUTPUT_DIR", str(tmp_path / "isolated-live"))
