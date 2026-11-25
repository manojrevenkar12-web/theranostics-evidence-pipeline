"""Settings live in config/*.json; nothing tunable is hard-coded."""

from __future__ import annotations

import hashlib
import json
import os
from functools import cache
from pathlib import Path
from typing import Any


def root() -> Path:
    env = os.environ.get("TEP_ROOT")
    if env:
        return Path(env)
    here = Path.cwd()
    for p in [here, *here.parents]:
        if (p / "config" / "world.json").exists():
            return p
    return Path(__file__).resolve().parents[2]


@cache
def _load(name: str, base: str) -> dict[str, Any]:
    with open(Path(base) / "config" / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def load(name: str) -> dict[str, Any]:
    return _load(name, str(root()))


def config_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((root() / "config").glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()
