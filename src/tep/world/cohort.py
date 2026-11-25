"""The hidden truth: patients, their lesions, therapy, response and where they were scanned."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np

from tep import config
from tep.rng import keyed

VOXEL_ML = 0.125  # 5 mm isotropic voxels

FAMILY = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
          "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
          "Hartmann", "Lange", "Werner", "Krause", "Lehmann", "Köhler", "Walter", "Mayer", "König", "Huber",
          "Smith", "Johnson", "Brown", "Taylor", "Wilson", "Davies", "Evans", "Thomas", "Roberts", "Walker",
          "O'Brien", "Nguyen", "Kowalski", "Rossi", "García", "Novak", "Yilmaz", "Petrov", "Andersen", "Murphy"]
GIVEN = ["Hans", "Peter", "Klaus", "Jürgen", "Wolfgang", "Michael", "Thomas", "Andreas", "Stefan", "Uwe",
         "John", "David", "Robert", "James", "William", "Richard", "Joseph", "Paul", "Mark", "George"]


@dataclass(frozen=True)
class Lesion:
    id: str
    region: str
    center: tuple[float, float, float]
    radius: float
    suv: float
    new: bool = False


@dataclass
class Scan:
    scan_id: str
    visit: str  # baseline | followup
    site: str
    date: dt.date
    tracer: str
    dose_mbq: float
    uptake_min: float
    weight_kg: float
    lesions: list[Lesion]
    organs: dict[str, tuple[tuple[float, float, float], tuple[int, int, int], float]]
    acquisition_hhmm: tuple[int, int]


@dataclass
class Patient:
    key: str
    family: str
    given: str
    birth_date: dt.date
    age: int
    expression: float
    liver_mets: bool
    psa_baseline: float
    psa_followup: float
    psa50: bool
    p_response: float
    recip: str
    tv_baseline: float
    tv_followup: float
    new_lesions: int
    baseline_site: str
    followup_site: str
    novel_agent: bool
    cycles: list[tuple[int, dt.date, str, float]] = field(default_factory=list)
    scans: list[Scan] = field(default_factory=list)


def sphere_count(radius: float) -> int:
    r = int(math.ceil(radius))
    g = np.arange(-r, r + 1)
    x, y, z = np.meshgrid(g, g, g, indexing="ij")
    return int(((x**2 + y**2 + z**2) <= radius**2).sum())


def lesion_ml(radius: float) -> float:
    return sphere_count(radius) * VOXEL_ML


def recip(tv0: float, tv1: float, new: int) -> str:
    """RECIP 1.0 from total PSMA tumour volume and new lesions."""
    if tv1 <= 0:
        return "CR"
    change = (tv1 - tv0) / tv0 if tv0 > 0 else math.inf
    if change <= -0.30 and new == 0:
        return "PR"
    if change >= 0.20 and new > 0:
        return "PD"
    return "SD"


def _pick_site(sites: dict, u: float) -> str:
    acc = 0.0
    for name, s in sites.items():
        acc += s["share"]
        if u <= acc:
            return name
    return list(sites)[-1]


def _organs(w: dict, rng: np.random.Generator) -> dict:
    out = {}
    j = w["organJitterVoxels"]
    for name, o in w["organs"].items():
        c = tuple(float(v + rng.integers(-j, j + 1)) for v in o["center"])
        suv = max(1.0, float(rng.normal(o["suv"][0], o["suv"][1])))
        out[name] = (c, tuple(o["radii"]), suv)
    return out


def _inside_organ(p: tuple[float, float, float], organs: dict, skip: set[str]) -> bool:
    for name, (c, r, _) in organs.items():
        if name in skip:
            continue
        d = sum(((p[i] - c[i]) / (r[i] + 3.5)) ** 2 for i in range(3))
        if d <= 1.0:
            return True
    return False


def _lesions(w: dict, rng: np.random.Generator, organs: dict, expression: float, n: int, liver: bool, prefix: str) -> list[Lesion]:
    pw = w["patient"]
    regions = list(w["regionWeights"])
    probs = np.array([w["regionWeights"][r] for r in regions])
    if not liver:
        probs[regions.index("liver")] = 0
    probs = probs / probs.sum()
    out: list[Lesion] = []
    if liver:
        forced = ["liver"]
    else:
        forced = []
    tries = 0
    while len(out) < n and tries < n * 30:
        tries += 1
        region = forced.pop() if forced else str(rng.choice(regions, p=probs))
        spec = w["regions"][region]
        base = spec["centers"][int(rng.integers(len(spec["centers"])))]
        s = spec["spread"]
        c = (float(base[0] + rng.uniform(-s, s)), float(base[1] + rng.uniform(-s, s)), float(base[2] + rng.uniform(-s, s)))
        skip = {"liver"} if region == "liver" else set()
        if _inside_organ(c, organs, skip):
            continue
        if any(sum((c[i] - o.center[i]) ** 2 for i in range(3)) < (o.radius + 2.5) ** 2 for o in out):
            continue
        radius = float(rng.uniform(*pw["lesionRadius"]))
        suv = float(np.clip(expression * rng.lognormal(0.0, 0.35), 3.0, 80.0))
        out.append(Lesion(f"{prefix}-L{len(out):02d}", region, c, radius, suv))
    return out


def _time_of_day(rng: np.random.Generator) -> tuple[int, int]:
    m = int(rng.integers(8 * 60, 16 * 60))
    return m // 60, m % 60


def cohort(seed: int, world: str) -> list[Patient]:
    """Every patient of one world (dev or heldout) for one seed. Depends on (seed, world) only."""
    w = config.load("world")
    sw = w["sitesByWorld"][world]
    pw = w["patient"]
    r = pw["response"]
    out: list[Patient] = []
    for i in range(sw["patients"]):
        rng = keyed(seed, world, "patient", i)
        key = f"{world[:1].upper()}{seed}-{i:04d}"
        family = str(rng.choice(FAMILY))
        given = str(rng.choice(GIVEN))
        age = int(rng.integers(*pw["ageYears"]))
        base_date = dt.date(2025, 1, 6) + dt.timedelta(days=int(rng.integers(0, 480)))
        birth = dt.date(base_date.year - age, int(rng.integers(1, 13)), int(rng.integers(1, 29)))
        expression = float(np.exp(rng.normal(pw["expressionLogMean"], pw["expressionLogSd"])))
        liver = bool(rng.random() < pw["liverMetsShare"])
        n = int(np.clip(round(np.exp(rng.normal(pw["lesionsLogMean"], pw["lesionsLogSd"]))), 1, pw["maxLesions"]))
        psa0 = float(np.exp(rng.normal(pw["psaLogMean"], pw["psaLogSd"])))
        weight = float(rng.uniform(*pw["weightKg"]))
        site0 = _pick_site(sw["sites"], float(rng.random()))
        site1 = site0
        if rng.random() < sw["referralShare"]:
            others = [s for s in sw["sites"] if s != site0]
            site1 = str(rng.choice(others))
        organs0 = _organs(w, rng)
        les0 = _lesions(w, rng, organs0, expression, n, liver, f"{key}-B")
        tv0 = sum(lesion_ml(x.radius) for x in les0)
        z = (r["intercept"] + r["expression"] * (math.log(expression) - pw["expressionLogMean"]) / pw["expressionLogSd"]
             + r["volume"] * (math.log1p(tv0) - 2.0) + r["liver"] * liver
             + r["psa"] * (math.log(psa0) - pw["psaLogMean"]) / pw["psaLogSd"])
        p = 1 / (1 + math.exp(-z))
        responder = bool(rng.random() < p)
        fu = pw["followUp"]
        les1: list[Lesion] = []
        for les in les0:
            if responder:
                f = float(rng.uniform(*fu["responderShrink"]))
                rad = les.radius * f ** (1 / 3)
                if rad < 0.9:
                    continue
                les1.append(Lesion(les.id.replace("-B", "-F"), les.region, les.center, rad, max(3.0, les.suv * 0.6)))
            else:
                f = float(rng.uniform(*fu["progressorGrow"]))
                les1.append(Lesion(les.id.replace("-B", "-F"), les.region, les.center, min(3.2, les.radius * f ** (1 / 3)), les.suv))
        organs1 = _organs(w, rng)
        new = 0
        if not responder and rng.random() < fu["newLesionShare"]:
            extra = _lesions(w, rng, organs1, expression, int(rng.integers(1, 4)), False, f"{key}-N")
            for e in extra:
                if all(sum((e.center[k] - o.center[k]) ** 2 for k in range(3)) > (o.radius + 3) ** 2 for o in les1):
                    les1.append(Lesion(e.id, e.region, e.center, e.radius, e.suv, new=True))
                    new += 1
        tv1 = sum(lesion_ml(x.radius) for x in les1)
        psa1 = psa0 * (float(rng.uniform(0.05, 0.45)) if responder else float(rng.uniform(0.6, 2.5)))
        th = w["therapy"]
        novel = bool(rng.random() < th["novelAgentShare"])
        agent = th["novelAgent"] if novel else th["agent"]
        c1 = base_date + dt.timedelta(days=int(rng.integers(7, 22)))
        cycles = [(k + 1, c1 + dt.timedelta(weeks=th["weeksBetweenCycles"] * k), agent, th["activityGBq"])
                  for k in range(th["cyclesBeforeFollowUp"])]
        fu_date = c1 + dt.timedelta(weeks=12) + dt.timedelta(days=int(rng.integers(-3, 4)))
        scans = []
        for visit, site, date, lesions, organs in (("baseline", site0, base_date, les0, organs0), ("followup", site1, fu_date, les1, organs1)):
            tracer = sw["sites"][site]["tracer"]
            tr = w["tracers"][tracer]
            scans.append(Scan(f"{key}-{visit[0].upper()}", visit, site, date, tracer, float(rng.uniform(*tr["doseMBq"])),
                              float(rng.uniform(*w["uptakeMinutes"])), weight, lesions, organs, _time_of_day(rng)))
        out.append(Patient(key, family, given, birth, age, expression, liver, psa0, psa1, responder, p,
                           recip(tv0, tv1, new), tv0, tv1, new, site0, site1, novel, cycles, scans))
    return out
