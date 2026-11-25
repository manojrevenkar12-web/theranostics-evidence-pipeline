import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def small_root(tmp_path, monkeypatch):
    """A copy of config/ with small worlds, so tests run in seconds."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    w = json.loads((tmp_path / "config" / "world.json").read_text())
    w["sitesByWorld"]["dev"]["patients"] = 24
    w["sitesByWorld"]["heldout"]["patients"] = 12
    (tmp_path / "config" / "world.json").write_text(json.dumps(w))
    monkeypatch.setenv("TEP_ROOT", str(tmp_path))
    return tmp_path
