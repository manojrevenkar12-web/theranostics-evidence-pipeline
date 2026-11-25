"""Data queries to sites: code decides which issues to raise; the letter names the series by the site's own
accession number and states each problem and the fix. A letter that would carry a name or birth date is not sent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tep.ingest.rules import Issue

FIX = {
    "en": {
        "weight": "Please send the patient's weight in kg at the time of the scan.",
        "weightUnits": "Please confirm the patient's weight in kg; the value looks like grams.",
        "doseUnits": "Please confirm the injected activity in Bq; the value looks like MBq.",
        "uptakeTime": "Please confirm the injection time and the scan start time.",
        "missingSlice": "Please re-send the complete series.",
        "units": "Please confirm the pixel units.",
        "decay": "Please confirm the decay-correction reference (START or ADMIN).",
        "calibration": "Liver reference uptake at your site differs from the other sites. Please send the latest phantom cross-calibration factor.",
    },
    "de": {
        "weight": "Bitte senden Sie das Körpergewicht in kg zum Zeitpunkt der Untersuchung.",
        "weightUnits": "Bitte bestätigen Sie das Körpergewicht in kg; der Wert sieht nach Gramm aus.",
        "doseUnits": "Bitte bestätigen Sie die applizierte Aktivität in Bq; der Wert sieht nach MBq aus.",
        "uptakeTime": "Bitte bestätigen Sie Injektionszeit und Startzeit der Aufnahme.",
        "missingSlice": "Bitte senden Sie die vollständige Serie erneut.",
        "units": "Bitte bestätigen Sie die Einheit der Pixelwerte.",
        "decay": "Bitte bestätigen Sie den Bezugspunkt der Zerfallskorrektur (START oder ADMIN).",
        "calibration": "Die Leber-Referenzaufnahme an Ihrem Standort weicht von den anderen Standorten ab. Bitte senden Sie den aktuellen Phantom-Kreuzkalibrierfaktor.",
    },
}
INTRO = {"en": "Data query for series {ref}:", "de": "Datenrückfrage zur Serie {ref}:"}


@dataclass(frozen=True)
class Query:
    site: str
    reference: str
    issues: tuple[str, ...]
    text: str


def draft(site: str, language: str, reference: str, issues: list[Issue]) -> Query:
    codes = tuple(sorted({i.code for i in issues if i.blocking}))
    lines = [INTRO[language].format(ref=reference)]
    for i in issues:
        if i.blocking:
            lines.append(f"- {i.message} {FIX[language].get(i.code, '')}".rstrip())
    return Query(site, reference, codes, "\n".join(lines))


def calibration_query(site: str, language: str, deviation: float) -> Query:
    pct = f"{deviation * 100:+.0f}%"
    head = INTRO[language].format(ref=f"{site} ({pct})")
    return Query(site, site, ("calibration",), head + "\n- " + FIX[language]["calibration"])


def safe(q: Query, forbidden: list[str]) -> bool:
    """No identifier of any patient may appear in a letter."""
    low = q.text.lower()
    return not any(f and re.search(r"\b" + re.escape(f.lower()) + r"\b", low) for f in forbidden)
