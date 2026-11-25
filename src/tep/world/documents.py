"""Clinical documents written from the truth: PET reports, therapy letters, lab results, in English or German.

Each document carries the facts it states, so extraction can be scored. Some documents use terms the seed
vocabulary does not know (a newer therapy agent, the miPSMA score) and a few contain typos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from tep import config
from tep.rng import keyed
from tep.world.cohort import Patient, Scan
from tep.world.dicom_out import mrn, transliterate

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NOVEL = {"177Lu-PSMA-I&T": ("agent", ["[177Lu]Lu-PSMA-I&T", "Lu-PSMA-I&T"]), "miPSMA score": ("score", ["miPSMA score"])}

REGION_TEXT = {
    "en": {"prostate": ["prostate bed", "prostate"], "pelvicLN": ["pelvic lymph node", "iliac lymph node"],
           "retroLN": ["retroperitoneal lymph node", "paraaortic node"], "bone": ["osseous lesion", "vertebra"],
           "lung": ["pulmonary nodule", "lung"], "liver": ["hepatic lesion", "liver"]},
    "de": {"prostate": ["Prostataloge", "Prostata"], "pelvicLN": ["Beckenlymphknoten", "iliakaler Lymphknoten"],
           "retroLN": ["retroperitonealer Lymphknoten", "paraaortaler Lymphknoten"], "bone": ["ossäre Läsion", "Wirbelkörper"],
           "lung": ["pulmonaler Rundherd", "Lunge"], "liver": ["hepatische Läsion", "Leber"]},
}
TRACER_TEXT = {"Ga68-PSMA-11": ["[68Ga]Ga-PSMA-11", "Ga-68 PSMA-11"], "F18-PSMA-1007": ["[18F]PSMA-1007", "F-18 PSMA-1007"]}
AGENT_TEXT = {"177Lu-PSMA-617": ["[177Lu]Lu-PSMA-617", "Lu-PSMA-617"], "177Lu-PSMA-I&T": NOVEL["177Lu-PSMA-I&T"][1]}


@dataclass
class Fact:
    kind: str  # scan | finding | therapy | psa | score
    term: str  # world term: region name, tracer, agent, 'PSA', 'miPSMA score'
    date: dt.date
    value: float | None
    span: str  # the sentence that states it


@dataclass
class Document:
    doc_id: str
    patient_key: str
    site: str
    language: str
    kind: str
    text: str
    facts: list[Fact] = field(default_factory=list)
    novel_terms: list[str] = field(default_factory=list)
    noise_terms: list[str] = field(default_factory=list)


def fmt_date(d: dt.date, lang: str, style: int) -> str:
    if lang == "de":
        return d.strftime("%d.%m.%Y")
    return d.isoformat() if style == 0 else f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def fmt_num(x: float, lang: str, digits: int = 1) -> str:
    s = f"{x:.{digits}f}"
    return s.replace(".", ",") if lang == "de" else s


def _header(p: Patient, site: str, lang: str, seed: int) -> str:
    home = site == p.baseline_site
    fam = p.family if home else transliterate(p.family)
    if lang == "de":
        return f"Patient: {fam}, {p.given}, geb. {p.birth_date.strftime('%d.%m.%Y')}, MRN {mrn(seed, site, p.key)}\n"
    return f"Patient: {fam}, {p.given}; DOB {p.birth_date.isoformat()}; MRN {mrn(seed, site, p.key)}\n"


def _pick(rng, xs: list[str]) -> str:
    return xs[int(rng.integers(len(xs)))]


def pet_report(seed: int, world: str, p: Patient, scan: Scan) -> Document:
    w = config.load("world")
    lang = w["sitesByWorld"][world]["sites"][scan.site]["language"]
    rng = keyed(seed, "report", scan.scan_id)
    style = int(rng.integers(2))
    d = fmt_date(scan.date, lang, style)
    doc = Document(f"{scan.scan_id}-RPT", p.key, scan.site, lang, "pet_report", _header(p, scan.site, lang, seed))
    tracer = _pick(rng, TRACER_TEXT[scan.tracer])
    s = (f"PSMA-PET/CT mit {tracer} am {d}." if lang == "de" else f"PSMA-PET/CT with {tracer} on {d}.")
    doc.text += s + "\n"
    doc.facts.append(Fact("scan", scan.tracer, scan.date, None, s))
    by_region: dict[str, float] = {}
    for les in scan.lesions:
        by_region[les.region] = max(by_region.get(les.region, 0.0), les.suv)
    for region, suv in sorted(by_region.items()):
        phrase = _pick(rng, REGION_TEXT[lang][region])
        if rng.random() < w["reports"]["noiseTypoShare"]:
            word = phrase.split()[-1]
            cut = int(rng.integers(1, max(2, len(word) - 1)))
            typo = word[:cut] + word[cut + 1:]
            s = (f"Fraglicher Befund {typo} am {d}." if lang == "de" else f"Equivocal {typo} on {d}.")
            doc.text += s + "\n"
            doc.noise_terms.append(typo)
        s = (f"PSMA-avide {phrase} (SUVmax {fmt_num(suv, lang)}) am {d}." if lang == "de"
             else f"PSMA-avid {phrase} (SUVmax {fmt_num(suv, lang)}) on {d}.")
        doc.text += s + "\n"
        doc.facts.append(Fact("finding", region, scan.date, round(suv, 1), s))
    psa = p.psa_baseline if scan.visit == "baseline" else p.psa_followup
    s = (f"PSA {fmt_num(psa, lang, 2)} ng/ml am {d}." if lang == "de" else f"PSA {fmt_num(psa, lang, 2)} ng/ml on {d}.")
    doc.text += s + "\n"
    doc.facts.append(Fact("psa", "PSA", scan.date, round(psa, 2), s))
    if rng.random() < w["reports"]["novelTermShare"] * 2.5:
        score = int(rng.integers(1, 4))
        s = f"miPSMA score {score} am {d}." if lang == "de" else f"miPSMA score {score} on {d}."
        doc.text += s + "\n"
        doc.facts.append(Fact("score", "miPSMA score", scan.date, float(score), s))
        doc.novel_terms.append("miPSMA score")
    return doc


def therapy_letter(seed: int, world: str, p: Patient, cycle: tuple[int, dt.date, str, float]) -> Document:
    n, date, agent, gbq = cycle
    site = p.baseline_site
    lang = config.load("world")["sitesByWorld"][world]["sites"][site]["language"]
    rng = keyed(seed, "letter", p.key, n)
    doc = Document(f"{p.key}-C{n}", p.key, site, lang, "therapy_letter", _header(p, site, lang, seed))
    a = _pick(rng, AGENT_TEXT[agent])
    d = fmt_date(date, lang, int(rng.integers(2)))
    s = (f"Zyklus {n}: {a} mit {fmt_num(gbq, lang)} GBq am {d} appliziert." if lang == "de"
         else f"Cycle {n}: {a}, {fmt_num(gbq, lang)} GBq, administered on {d}.")
    doc.text += s + "\n"
    doc.facts.append(Fact("therapy", agent, date, gbq, s))
    if agent in NOVEL:
        doc.novel_terms.append(agent)
    return doc


def documents(seed: int, world: str, patients: list[Patient]) -> list[Document]:
    out: list[Document] = []
    for p in patients:
        for scan in p.scans:
            out.append(pet_report(seed, world, p, scan))
        for c in p.cycles:
            out.append(therapy_letter(seed, world, p, c))
    return out
