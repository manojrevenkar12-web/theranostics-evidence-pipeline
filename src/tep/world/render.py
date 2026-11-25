"""Renders the true SUV volume of a scan: body, organs with physiological uptake, lesions, blur and noise."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from tep import config
from tep.rng import keyed
from tep.world.cohort import Lesion, Scan


def grid() -> tuple[tuple[int, int, int], tuple[float, float, float]]:
    g = config.load("world")["grid"]
    return tuple(g["shape"]), tuple(g["spacingMm"])  # type: ignore[return-value]


def _coords(shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2]), indexing="ij")


def ellipsoid(shape, center, radii) -> np.ndarray:
    x, y, z = _coords(shape)
    return ((x - center[0]) / radii[0]) ** 2 + ((y - center[1]) / radii[1]) ** 2 + ((z - center[2]) / radii[2]) ** 2 <= 1.0


def sphere(shape, center, radius: float) -> np.ndarray:
    x, y, z = _coords(shape)
    return (x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2 <= radius**2


def lesion_mask(shape, les: Lesion) -> np.ndarray:
    c = tuple(round(v) for v in les.center)
    return sphere(shape, c, les.radius)


def body_mask(shape) -> np.ndarray:
    g = config.load("world")["grid"]
    x, y, _ = _coords(shape)
    r = g["bodyRadiusVoxels"]
    return ((x - shape[0] / 2) / r) ** 2 + ((y - shape[1] / 2 - 2) / (r * 0.8)) ** 2 <= 1.0


def suv_volume(seed: int, scan: Scan) -> np.ndarray:
    """The SUV a perfect scanner and a perfect pipeline would report for this scan."""
    g = config.load("world")["grid"]
    shape, _ = grid()
    v = np.zeros(shape, dtype=np.float64)
    v[body_mask(shape)] = g["backgroundSuv"]
    for _, (c, r, suv) in scan.organs.items():
        v[ellipsoid(shape, c, r)] = suv
    for les in scan.lesions:
        m = lesion_mask(shape, les)
        v[m] = np.maximum(v[m], les.suv)
    v = gaussian_filter(v, g["psfSigmaVoxels"])
    noise = keyed(seed, "noise", scan.scan_id).normal(1.0, g["noise"], size=shape)
    return np.clip(v * noise, 0.0, None)
