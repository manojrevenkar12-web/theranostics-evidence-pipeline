"""Builds the 3D volume of a series and its NIfTI affine (DICOM LPS to NIfTI RAS)."""

from __future__ import annotations

import nibabel as nib
import numpy as np

from tep.ingest.series import Series


def ordered(s: Series, by_position: bool = True) -> list:
    if by_position:
        return sorted(s.slices, key=lambda x: x.z)
    return sorted(s.slices, key=lambda x: x.instance)


def stack(s: Series, by_position: bool = True) -> np.ndarray:
    """Volume indexed (x=column, y=row, z=slice), in the stored units (Bq/mL)."""
    return np.stack([sl.pixels.T for sl in ordered(s, by_position)], axis=2)


def affine_ras(s: Series) -> np.ndarray:
    h = s.header
    iop = np.array([float(v) for v in h.ImageOrientationPatient])
    row_dir, col_dir = iop[:3], iop[3:]
    normal = np.cross(row_dir, col_dir)
    dy, dx = (float(v) for v in h.PixelSpacing)
    first = ordered(s, True)[0]
    zs = sorted(x.z for x in s.slices)
    dz = float(np.median(np.diff(zs))) if len(zs) > 1 else float(h.SliceThickness)
    origin = normal * first.z
    lps = np.eye(4)
    lps[:3, 0] = row_dir * dx
    lps[:3, 1] = col_dir * dy
    lps[:3, 2] = normal * dz
    lps[:3, 3] = origin
    return np.diag([-1.0, -1.0, 1.0, 1.0]) @ lps


def to_nifti(volume: np.ndarray, affine: np.ndarray) -> nib.Nifti1Image:
    img = nib.Nifti1Image(volume.astype(np.float32), affine)
    img.header.set_xyzt_units("mm")
    return img
