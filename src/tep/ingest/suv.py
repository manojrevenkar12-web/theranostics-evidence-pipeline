"""Body-weight SUV: activity concentration x weight / decay-corrected injected dose."""

from __future__ import annotations

from dataclasses import dataclass

from tep.ingest.rules import uptake_minutes
from tep.ingest.series import Series


@dataclass(frozen=True)
class Corrections:
    """Values a site confirmed in answer to a query; they replace the header's values."""

    weight_kg: float | None = None
    dose_bq: float | None = None
    uptake_min: float | None = None


NONE = Corrections()


def suv_factor(s: Series, corr: Corrections = NONE, respect_decay_reference: bool = True) -> float:
    """Multiply stored Bq/mL by this to get SUVbw.

    With DecayCorrection START the image is corrected to scan start, so the dose is decayed from injection to
    scan start. With ADMIN the image is already corrected to injection time, so the dose is used as injected.
    """
    h = s.header
    seq = h.RadiopharmaceuticalInformationSequence[0]
    weight_g = (corr.weight_kg if corr.weight_kg is not None else float(h.PatientWeight)) * 1000.0
    dose = corr.dose_bq if corr.dose_bq is not None else float(seq.RadionuclideTotalDose)
    half = float(seq.RadionuclideHalfLife)
    up = corr.uptake_min if corr.uptake_min is not None else uptake_minutes(s)
    decay = 1.0
    if str(h.DecayCorrection) == "START" or not respect_decay_reference:
        decay = 2 ** (-((up or 0.0) * 60.0) / half)
    return weight_g / (dose * decay)
