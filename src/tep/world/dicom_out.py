"""Writes each scan as a PET DICOM series the way its site would send it, defects included.

The defects are the world's secret: which series has a weight in grams, a dose in MBq, an injection
time after the scan, a missing slice, reversed instance numbers, a duplicate send, or names in free-text
tags. The pipeline only sees the files.
"""

from __future__ import annotations

import datetime as dt
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, ExplicitVRLittleEndian, generate_uid

from tep import config
from tep.rng import keyed, unit
from tep.world.cohort import Patient, Scan
from tep.world.render import grid, suv_volume

PET_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.128"
DEFECTS = ("weightGrams", "missingWeight", "doseMBq", "timeRollover", "instanceReversed", "missingSlice", "duplicateSend", "phiComments")


@dataclass
class SeriesTruth:
    scan_id: str
    patient_key: str
    site: str
    series_uid: str
    defects: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    missing_slice: int | None = None


def _uid(seed: int, *parts: object) -> str:
    return str(generate_uid(entropy_srcs=[str(seed), *map(str, parts)]))


def transliterate(name: str) -> str:
    """How another site's system may spell the same name: Müller -> MUELLER, García -> GARCIA."""
    s = name.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = s.replace("Ü", "Ue").replace("Ö", "Oe").replace("Ä", "Ae")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.upper()


def mrn(seed: int, site: str, patient_key: str) -> str:
    return f"{site[:3].upper()}{int(keyed(seed, 'mrn', site, patient_key).integers(10**6, 10**7))}"


def site_defects(seed: int, world: str, scan: Scan) -> list[str]:
    site = config.load("world")["sitesByWorld"][world]["sites"][scan.site]
    out = []
    for d in DEFECTS:
        p = site["defects"].get(d, 0.0)
        if p and unit(seed, "defect", scan.scan_id, d) < p:
            out.append(d)
    if "weightGrams" in out and "missingWeight" in out:
        out.remove("missingWeight")
    return out


def stored_activity(seed: int, world: str, scan: Scan, suv: np.ndarray) -> np.ndarray:
    """Bq/mL as the site's scanner stores it, under the site's decay convention and calibration."""
    w = config.load("world")
    site = w["sitesByWorld"][world]["sites"][scan.site]
    half = w["tracers"][scan.tracer]["halfLifeS"]
    dose_bq = scan.dose_mbq * 1e6
    if site["decay"] == "START":
        dose_bq *= 2 ** (-(scan.uptake_min * 60) / half)
    return suv * dose_bq / (scan.weight_kg * 1000.0) * site["calibration"]


def _tm(t: dt.datetime) -> str:
    return t.strftime("%H%M%S")


def _base(seed: int, world: str, p: Patient, scan: Scan, defects: list[str]) -> Dataset:
    w = config.load("world")
    site = scan.site
    home = site == p.baseline_site
    ds = Dataset()
    ds.SOPClassUID = PET_SOP_CLASS
    ds.Modality = "PT"
    family = p.family if home else transliterate(p.family)
    ds.PatientName = f"{family}^{p.given}" if home else f"{family}^{p.given.upper()}"
    ds.PatientID = mrn(seed, site, p.key)
    ds.PatientBirthDate = p.birth_date.strftime("%Y%m%d")
    ds.PatientSex = "M"
    ds.PatientAge = f"{p.age:03d}Y"
    if "missingWeight" not in defects:
        ds.PatientWeight = f"{scan.weight_kg * (1000 if 'weightGrams' in defects else 1):.1f}"
    ds.InstitutionName = {"charite": "Charité Berlin", "tum": "Klinikum rechts der Isar", "uke": "UKE Hamburg"}.get(site, site.upper())
    ds.ReferringPhysicianName = "Dr^Referrer"
    ds.AccessionNumber = f"ACC{int(keyed(seed, 'acc', scan.scan_id).integers(10**7, 10**8))}"
    ds.StudyInstanceUID = _uid(seed, "study", scan.scan_id)
    ds.SeriesInstanceUID = _uid(seed, "series", scan.scan_id)
    ds.FrameOfReferenceUID = _uid(seed, "for", scan.scan_id)
    start = dt.datetime.combine(scan.date, dt.time(*scan.acquisition_hhmm))
    inj = start - dt.timedelta(minutes=scan.uptake_min)
    if "timeRollover" in defects:
        inj = inj + dt.timedelta(hours=2)
    ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = scan.date.strftime("%Y%m%d")
    ds.StudyTime = ds.SeriesTime = ds.AcquisitionTime = _tm(start)
    ds.SeriesDescription = f"PET WB {scan.tracer}"
    ds.Units = "BQML"
    ds.DecayCorrection = w["sitesByWorld"][world]["sites"][site]["decay"]
    ds.CorrectedImage = ["DECY", "ATTN", "SCAT"]
    rp = Dataset()
    rp.Radiopharmaceutical = scan.tracer
    dose = scan.dose_mbq if "doseMBq" in defects else scan.dose_mbq * 1e6
    rp.RadionuclideTotalDose = f"{dose:.1f}"
    rp.RadionuclideHalfLife = f"{w['tracers'][scan.tracer]['halfLifeS']:.1f}"
    rp.RadiopharmaceuticalStartTime = _tm(inj)
    ds.RadiopharmaceuticalInformationSequence = Sequence([rp])
    if "phiComments" in defects:
        ds.ImageComments = f"Pat. {p.family}, {p.given} *{p.birth_date.strftime('%d.%m.%Y')}"
        block = ds.private_block(0x0011, "SITE_PACS", create=True)
        block.add_new(0x01, "LO", f"{p.family}^{p.given}")
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    shape, spacing = grid()
    ds.PixelSpacing = [spacing[1], spacing[0]]
    ds.SliceThickness = spacing[2]
    ds.Rows, ds.Columns = shape[1], shape[0]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleIntercept = 0
    ds.NumberOfSlices = shape[2]
    return ds


def write_scan(seed: int, world: str, p: Patient, scan: Scan, out: Path, resend: bool = False) -> SeriesTruth:
    """Writes the series as the site sends it. A resend, in answer to a query, comes without the missing slice."""
    defects = site_defects(seed, world, scan)
    if resend:
        defects = [d for d in defects if d not in ("missingSlice", "duplicateSend")]
    base = _base(seed, world, p, scan, defects)
    shape, spacing = grid()
    act = stored_activity(seed, world, scan, suv_volume(seed, scan))
    n = shape[2]
    skip = None
    if "missingSlice" in defects:
        skip = int(keyed(seed, "skip", scan.scan_id).integers(8, n - 8))
    truth = SeriesTruth(scan.scan_id, p.key, scan.site, str(base.SeriesInstanceUID), defects, missing_slice=skip)
    sends = ["resend"] if resend else (["send1", "send2"] if "duplicateSend" in defects else ["send1"])
    for send in sends:
        folder = out / scan.site / f"{base.AccessionNumber}_{send}"
        folder.mkdir(parents=True, exist_ok=True)
        truth.folders.append(str(folder))
        for k in range(n):
            if k == skip:
                continue
            ds = FileDataset(str(folder / f"IM{k:04d}.dcm"), Dataset(), file_meta=FileMetaDataset(), preamble=b"\0" * 128)
            ds.update(base)
            sl = act[:, :, k].T  # rows = y, columns = x
            top = float(sl.max())
            slope = top / 32000.0 if top > 0 else 1.0
            ds.RescaleSlope = f"{slope:.6g}"
            slope = float(ds.RescaleSlope)
            ds.PixelData = np.round(sl / slope).astype(np.int16).tobytes()
            ds.InstanceNumber = (n - k) if "instanceReversed" in defects else (k + 1)
            ds.ImagePositionPatient = [0.0, 0.0, float(k * spacing[2])]
            ds.SliceLocation = float(k * spacing[2])
            ds.SOPInstanceUID = _uid(seed, "sop", scan.scan_id, k)
            ds.file_meta.MediaStorageSOPClassUID = UID(PET_SOP_CLASS)
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.save_as(folder / f"IM{k:04d}.dcm", enforce_file_format=True)
    return truth


def site_answers(seed: int, world: str, scan_id: str, site: str, issue: str) -> bool:
    """Whether the site answers a data query about this issue (the world decides, keyed, not the pipeline)."""
    p = config.load("world")["sitesByWorld"][world]["sites"][site]["answers"]
    return unit(seed, "answer", scan_id, issue) < p


def true_value(scan: Scan, issue: str, world: str) -> float:
    w = config.load("world")
    if issue in ("weight", "weightUnits"):
        return scan.weight_kg
    if issue == "doseUnits":
        return scan.dose_mbq * 1e6
    if issue == "uptakeTime":
        return scan.uptake_min
    if issue == "calibration":
        return w["sitesByWorld"][world]["sites"][scan.site]["calibration"]
    return math.nan
