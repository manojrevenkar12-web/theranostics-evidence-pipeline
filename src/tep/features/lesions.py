"""Lesion segmentation and quantification on an SUV volume.

Physiological uptake (kidneys, salivary glands, bladder, spleen) is excluded with an atlas; in the liver,
where background uptake is high, a lesion must exceed a multiple of the liver's own reference uptake.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from tep import config
from tep.world.render import ellipsoid

VOXEL_ML = 0.125


@dataclass(frozen=True)
class Component:
    voxels: int
    volume_ml: float
    suv_max: float
    suv_mean: float
    centroid: tuple[float, float, float]
    region: str
    mask_index: int


@dataclass
class ScanFeatures:
    components: list[Component]
    labels: np.ndarray
    liver_reference: float
    tv_ml: float
    suv_mean: float
    suv_max: float
    lesion_count: int
    liver_involved: bool
    bone_count: int


def atlas(shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """(physiological uptake mask to exclude, liver zone), from the configured anatomy, dilated for safety.

    The liver zone includes a ring around the liver, where blurred liver uptake would otherwise pass the
    global threshold; there the liver rule applies.
    """
    w = config.load("world")
    r = config.load("rules")["segmentation"]
    excl = np.zeros(shape, dtype=bool)
    liver = np.zeros(shape, dtype=bool)
    d = r["atlasDilateVoxels"]
    for name, o in w["organs"].items():
        m = ellipsoid(shape, o["center"], [x + d for x in o["radii"]])
        if name == "liver":
            liver |= ellipsoid(shape, o["center"], [x + r["liverRingVoxels"] for x in o["radii"]])
        else:
            excl |= m
    return excl, liver


def liver_reference(suv: np.ndarray) -> float:
    r = config.load("rules")["calibration"]
    o = config.load("world")["organs"]["liver"]
    liver = ellipsoid(suv.shape, o["center"], o["radii"])
    core = ndimage.binary_erosion(liver, iterations=r["erodeVoxels"])
    return float(np.median(suv[core]))


def region_of(c: tuple[float, float, float]) -> str:
    w = config.load("world")
    best, bd = "unknown", 1e9
    for name, spec in w["regions"].items():
        for cc in spec["centers"]:
            d = sum((c[i] - cc[i]) ** 2 for i in range(3))
            if d < bd:
                best, bd = name, d
    return best


def segment(suv: np.ndarray) -> ScanFeatures:
    r = config.load("rules")["segmentation"]
    excl, liver = atlas(suv.shape)
    ref = liver_reference(suv)
    cand = (suv >= r["suvThreshold"]) & ~excl & ~liver
    cand |= liver & ~excl & (suv >= r["liverFactor"] * ref) & (suv >= r["suvThreshold"])
    labels, n = ndimage.label(cand, structure=np.ones((3, 3, 3)))
    comps: list[Component] = []
    for i in range(1, n + 1):
        m = labels == i
        k = int(m.sum())
        if k < r["minVoxels"]:
            labels[m] = 0
            continue
        vals = suv[m]
        c = tuple(float(x) for x in ndimage.center_of_mass(m))
        reg = "liver" if liver[tuple(int(round(x)) for x in c)] else region_of(c)  # type: ignore[arg-type]
        comps.append(Component(k, k * VOXEL_ML, float(vals.max()), float(vals.mean()), c, reg, i))  # type: ignore[arg-type]
    tv = sum(x.volume_ml for x in comps)
    vox = sum(x.voxels for x in comps)
    mean = sum(x.suv_mean * x.voxels for x in comps) / vox if vox else 0.0
    return ScanFeatures(comps, labels, ref, tv, mean, max((x.suv_max for x in comps), default=0.0), len(comps),
                        any(x.region == "liver" for x in comps), sum(x.region == "bone" for x in comps))


def new_lesions(base: ScanFeatures, follow: ScanFeatures, distance_voxels: float = 3.0) -> int:
    n = 0
    for f in follow.components:
        if all(sum((f.centroid[i] - b.centroid[i]) ** 2 for i in range(3)) > distance_voxels**2 for b in base.components):
            n += 1
    return n


def recip(tv0: float, tv1: float, new: int) -> str:
    r = config.load("rules")["recip"]
    if tv1 <= 0:
        return "CR"
    ch = (tv1 - tv0) / tv0 if tv0 > 0 else float("inf")
    if ch <= r["prDecline"] and new == 0:
        return "PR"
    if ch >= r["pdIncrease"] and new > 0:
        return "PD"
    return "SD"
