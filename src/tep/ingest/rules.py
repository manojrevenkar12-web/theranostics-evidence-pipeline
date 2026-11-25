"""Plausibility rules. A rule that fails blocks the series and names the fix the site must make; nothing is guessed."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from tep import config
from tep.ingest.series import Series


@dataclass(frozen=True)
class Issue:
    code: str  # weight | weightUnits | doseUnits | uptakeTime | missingSlice | units | decay | instanceOrder | duplicates | phiText
    blocking: bool
    field: str
    observed: str
    message: str


def tracer_of(s: Series) -> str:
    seq = s.header.get("RadiopharmaceuticalInformationSequence")
    return str(seq[0].Radiopharmaceutical) if seq else ""


def uptake_minutes(s: Series) -> float | None:
    seq = s.header.get("RadiopharmaceuticalInformationSequence")
    if not seq or "RadiopharmaceuticalStartTime" not in seq[0]:
        return None
    t0 = dt.datetime.strptime(str(seq[0].RadiopharmaceuticalStartTime)[:6], "%H%M%S")
    t1 = dt.datetime.strptime(str(s.header.SeriesTime)[:6], "%H%M%S")
    return (t1 - t0).total_seconds() / 60.0


def slice_gaps(s: Series, tol: float) -> list[int]:
    zs = sorted(x.z for x in s.slices)
    if len(zs) < 3:
        return []
    d = np.diff(zs)
    step = float(np.median(d))
    return [i for i, v in enumerate(d) if abs(v - step) > tol]


def check(s: Series, *, units: bool = True, timing: bool = True, slices: bool = True) -> list[Issue]:
    r = config.load("rules")
    h = s.header
    out: list[Issue] = []
    tracer = tracer_of(s)
    if units:
        w = h.get("PatientWeight")
        if w is None or str(w) == "":
            out.append(Issue("weight", True, "PatientWeight", "missing", "Patient weight is missing; SUV cannot be computed."))
        else:
            wv = float(w)
            if not (r["weightKg"][0] <= wv <= r["weightKg"][1]):
                hint = " (looks like grams)" if 30_000 <= wv <= 250_000 else ""
                out.append(Issue("weightUnits", True, "PatientWeight", f"{wv:g}", f"Patient weight {wv:g} kg is outside {r['weightKg']} kg{hint}."))
        seq = h.get("RadiopharmaceuticalInformationSequence")
        if not seq:
            out.append(Issue("doseUnits", True, "RadionuclideTotalDose", "missing", "Radiopharmaceutical information is missing."))
        else:
            dose_mbq = float(seq[0].RadionuclideTotalDose) / 1e6
            lo, hi = r["doseMBq"].get(tracer, [10, 1000])
            if not (lo <= dose_mbq <= hi):
                hint = " (looks like MBq, not Bq)" if lo <= dose_mbq * 1e6 <= hi else ""
                out.append(Issue("doseUnits", True, "RadionuclideTotalDose", f"{float(seq[0].RadionuclideTotalDose):g}",
                                 f"Injected dose {dose_mbq:g} MBq is outside {lo}-{hi} MBq for {tracer}{hint}."))
        if str(h.get("Units", "")) not in r["units"]:
            out.append(Issue("units", True, "Units", str(h.get("Units", "")), "Pixel units are not Bq/mL."))
        if str(h.get("DecayCorrection", "")) not in r["decayCorrection"]:
            out.append(Issue("decay", True, "DecayCorrection", str(h.get("DecayCorrection", "")), "Decay-correction reference is unknown."))
    if timing:
        up = uptake_minutes(s)
        lo, hi = r["uptakeMinutes"]
        if up is None or not (lo <= up <= hi):
            out.append(Issue("uptakeTime", True, "RadiopharmaceuticalStartTime", "missing" if up is None else f"{up:.0f} min",
                             f"Uptake time {'missing' if up is None else f'{up:.0f} min'} is outside {lo}-{hi} min; injection or scan time is wrong."))
    if slices:
        gaps = slice_gaps(s, r["sliceSpacingToleranceMm"])
        n = int(h.get("NumberOfSlices", len(s.slices)))
        if gaps or len(s.slices) != n:
            out.append(Issue("missingSlice", True, "ImagePositionPatient", f"{len(s.slices)} of {n} slices",
                             f"{n - len(s.slices)} slice(s) missing; the series must be re-sent."))
        inst = [x.instance for x in sorted(s.slices, key=lambda x: x.z)]
        if inst != sorted(inst):
            out.append(Issue("instanceOrder", False, "InstanceNumber", "descending",
                             "Instance numbers run against slice position; slices are ordered by position."))
    if s.duplicate_instances:
        out.append(Issue("duplicates", False, "SOPInstanceUID", str(s.duplicate_instances),
                         f"{s.duplicate_instances} instance(s) received twice; kept once."))
    if "ImageComments" in h or any(t.is_private for t in h):
        out.append(Issue("phiText", False, "ImageComments/private tags", "present", "Free-text or private tags present; removed on de-identification."))
    return out
