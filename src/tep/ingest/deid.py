"""De-identification: an allowlist of header fields, keyed pseudonyms, per-patient date shifts, scrubbed text.

Keeping a list of what may leave is safer than a list of what must not: a private tag or free-text field
nobody thought of is dropped by default.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import unicodedata
from typing import Any

from pydicom.dataset import Dataset

DEV_KEY = b"dev-only-deid-key-not-for-real-data"

KEEP = ["Modality", "Units", "DecayCorrection", "CorrectedImage", "PatientSex", "PatientAge", "PatientWeight",
        "SliceThickness", "PixelSpacing", "ImageOrientationPatient", "Rows", "Columns", "NumberOfSlices",
        "SeriesDescription", "SeriesTime", "AcquisitionTime"]
DATES = ["StudyDate", "SeriesDate", "AcquisitionDate"]
UIDS = ["StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def key() -> bytes:
    k = os.environ.get("TEP_DEID_KEY")
    return k.encode() if k else DEV_KEY


def _mac(*parts: str) -> str:
    return hmac.new(key(), "|".join(parts).encode(), hashlib.sha256).hexdigest()


def normalise_name(name: str) -> str:
    s = name.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae").replace("ß", "ss")
    s = s.replace("Ü", "UE").replace("Ö", "OE").replace("Ä", "AE")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z^]", "", s)


def linkage_key(patient_name: str, birth_date: str) -> str:
    """Same person at two sites: names normalised (MÜLLER = MUELLER), plus date of birth."""
    return f"{normalise_name(patient_name)}|{birth_date}"


def pseudonym(link: str) -> str:
    return "P-" + _mac("patient", link)[:12]


def date_offset_days(pseudo: str) -> int:
    return -(30 + int(_mac("shift", pseudo)[:8], 16) % 365)


def new_uid(uid: str) -> str:
    return "2.25." + str(int(_mac("uid", uid)[:30], 16))


def shift_da(value: str, days: int) -> str:
    d = dt.datetime.strptime(value[:8], "%Y%m%d").date() + dt.timedelta(days=days)
    return d.strftime("%Y%m%d")


def _plain(v: Any) -> Any:
    if isinstance(v, str):
        return v
    if hasattr(v, "__iter__"):
        return [_plain(x) for x in v]
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def header(ds: Dataset, pseudo: str) -> dict[str, Any]:
    """The de-identified header as plain data: allowlisted fields, shifted dates, new UIDs, pseudonym."""
    off = date_offset_days(pseudo)
    out: dict[str, Any] = {"PatientPseudonym": pseudo}
    for k in KEEP:
        if k in ds:
            out[k] = _plain(ds[k].value)
    for k in DATES:
        if k in ds:
            out[k] = shift_da(str(ds[k].value), off)
    for k in UIDS:
        if k in ds:
            out[k] = new_uid(str(ds[k].value))
    seq = ds.get("RadiopharmaceuticalInformationSequence")
    if seq:
        rp = seq[0]
        out["Radiopharmaceutical"] = str(rp.get("Radiopharmaceutical", ""))
        out["RadionuclideTotalDose"] = str(rp.get("RadionuclideTotalDose", ""))
        out["RadionuclideHalfLife"] = str(rp.get("RadionuclideHalfLife", ""))
        out["RadiopharmaceuticalStartTime"] = str(rp.get("RadiopharmaceuticalStartTime", ""))
    return out


def dataset(ds: Dataset, pseudo: str) -> Dataset:
    """A de-identified copy of one instance, for writing DICOM out."""
    h = header(ds, pseudo)
    out = Dataset()
    for k in KEEP:
        if k in ds:
            setattr(out, k, ds[k].value)
    for k in DATES + UIDS:
        if k in h:
            setattr(out, k, h[k])
    out.PatientName = pseudo
    out.PatientID = pseudo
    out.PatientIdentityRemoved = "YES"
    out.DeidentificationMethod = "tep allowlist; dates shifted per patient; UIDs remapped"
    if "SOPInstanceUID" in ds:
        out.SOPInstanceUID = new_uid(str(ds.SOPInstanceUID))
        out.SOPClassUID = ds.SOPClassUID
    for k in ("ImagePositionPatient", "InstanceNumber", "RescaleSlope", "RescaleIntercept", "BitsAllocated", "BitsStored",
              "HighBit", "PixelRepresentation", "SamplesPerPixel", "PhotometricInterpretation", "PixelData"):
        if k in ds:
            setattr(out, k, ds[k].value)
    if "RadiopharmaceuticalInformationSequence" in ds:
        out.RadiopharmaceuticalInformationSequence = ds.RadiopharmaceuticalInformationSequence
    return out


_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_EN = re.compile(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})\b")


def shift_text_dates(text: str, days: int) -> str:
    def iso(m: re.Match) -> str:
        return (dt.date(int(m[1]), int(m[2]), int(m[3])) + dt.timedelta(days=days)).isoformat()

    def de(m: re.Match) -> str:
        return (dt.date(int(m[3]), int(m[2]), int(m[1])) + dt.timedelta(days=days)).strftime("%d.%m.%Y")

    def en(m: re.Match) -> str:
        d = dt.date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1])) + dt.timedelta(days=days)
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"

    return _EN.sub(en, _DE.sub(de, _ISO.sub(iso, text)))


def text(doc: str, pseudo: str, names: list[str], ids: list[str], birth_date: str) -> str:
    """Scrubs a document: the header line, known names and identifiers, the birth date; then shifts every date."""
    lines = doc.splitlines()
    if lines and lines[0].startswith("Patient:"):
        lines[0] = f"Patient: {pseudo}"
    out = "\n".join(lines) + ("\n" if doc.endswith("\n") else "")
    for n in sorted({x for x in names if x}, key=len, reverse=True):
        out = re.sub(re.escape(n), "[NAME]", out, flags=re.IGNORECASE)
    for i in ids:
        out = out.replace(i, "[ID]")
    b = dt.datetime.strptime(birth_date, "%Y%m%d").date()
    for form in (b.isoformat(), b.strftime("%d.%m.%Y"), f"{b.day} {MONTHS[b.month - 1]} {b.year}"):
        out = out.replace(form, "[DOB]")
    return shift_text_dates(out, date_offset_days(pseudo))
