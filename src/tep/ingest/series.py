"""Reads a site's drop folder into series: one header, sorted slices, duplicates removed, checks recorded."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset


@dataclass
class Slice:
    path: str
    sha256: str
    sop_uid: str
    instance: int
    z: float
    pixels: np.ndarray  # rows x cols, already scaled to stored units (Bq/mL)


@dataclass
class Series:
    series_uid: str
    site: str
    header: Dataset
    slices: list[Slice] = field(default_factory=list)
    duplicate_instances: int = 0
    sources: list[str] = field(default_factory=list)  # file hashes, for lineage

    @property
    def key(self) -> str:
        return self.series_uid


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_slice(path: Path) -> tuple[Dataset, Slice]:
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array.astype(np.float64) * float(ds.get("RescaleSlope", 1.0)) + float(ds.get("RescaleIntercept", 0.0))
    pos = [float(v) for v in ds.ImagePositionPatient]
    iop = [float(v) for v in ds.ImageOrientationPatient]
    normal = np.cross(iop[:3], iop[3:])
    z = float(np.dot(pos, normal))
    return ds, Slice(str(path), sha256_file(path), str(ds.SOPInstanceUID), int(ds.InstanceNumber), z, arr)


def read_drop(drop: Path, dedupe: bool = True) -> list[Series]:
    """Groups every DICOM file under drop/<site>/ by series. With dedupe, a re-sent instance is kept once."""
    by_key: dict[str, Series] = {}
    for site_dir in sorted(p for p in drop.iterdir() if p.is_dir()):
        for folder in sorted(p for p in site_dir.iterdir() if p.is_dir()):
            for f in sorted(folder.glob("*.dcm")):
                ds, sl = read_slice(f)
                uid = str(ds.SeriesInstanceUID)
                key = uid if dedupe else f"{uid}#{folder.name}"
                s = by_key.get(key)
                if s is None:
                    hdr = ds.copy()
                    del hdr.PixelData
                    s = by_key[key] = Series(uid, site_dir.name, hdr)
                if dedupe and any(x.sop_uid == sl.sop_uid for x in s.slices):
                    s.duplicate_instances += 1
                    continue
                s.slices.append(sl)
                s.sources.append(sl.sha256)
    return list(by_key.values())
