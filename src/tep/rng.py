"""Keyed randomness: every draw depends on the seed and a key, never on what a design did."""

from __future__ import annotations

import hashlib

import numpy as np


def _key(seed: int, *key: object) -> int:
    h = hashlib.sha256(repr((seed, *key)).encode()).digest()
    return int.from_bytes(h[:8], "little")


def keyed(seed: int, *key: object) -> np.random.Generator:
    return np.random.default_rng(_key(seed, *key))


def unit(seed: int, *key: object) -> float:
    return float(keyed(seed, *key).random())
