"""The study: every design on the same worlds, gates, the held-out lock, and the evidence pack."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from tep import config
from tep.lab.process import SWITCHES, code_version, prepare, run
from tep.lineage.store import Lineage

LOWER = ["suvErrorMedian", "suvErrorOver10pctShare", "fpPerScan", "duplicateScans", "phiLeaks", "hallucinatedFactsKept",
         "wrongValuesKept", "noiseTermsInduced"]
HIGHER = ["usableScanShare", "pairedShare", "recipKappa", "lesionSensitivity", "factPrecision", "driftSiteFound"]


class Locked(Exception):
    pass


def designs() -> dict[str, Any]:
    return config.load("designs")


def _one_seed(args: tuple[int, str, bool]) -> dict[str, Any]:
    seed, split, with_evidence = args
    d = designs()
    names = d["main"] + d["ablations"]
    with tempfile.TemporaryDirectory() as tmp:
        prep = prepare(seed, split, Path(tmp))
        out: dict[str, Any] = {"seed": seed, "designs": {}}
        for n in names:
            off = set(d["designs"][n]["off"])
            lin = Lineage(code_version(), config.config_hash()) if (with_evidence and n == "pipeline") else None
            o = run(prep, off, lin)
            out["designs"][n] = o.measures
            if n == "pipeline":
                out["extras"] = o.extras
                if lin is not None:
                    out["lineage"] = lin.export()
                    out["lineageDigest"] = lin.digest()
    return out


def run_split(split: str, workers: int | None = None) -> dict[str, Any]:
    seeds = config.load("seeds")[split]
    workers = workers or int(os.environ.get("TEP_WORKERS", "2"))
    jobs = [(s, split, i == 0) for i, s in enumerate(seeds)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            per_seed = list(ex.map(_one_seed, jobs))
    else:
        per_seed = [_one_seed(j) for j in jobs]
    d = designs()
    names = d["main"] + d["ablations"]
    summary = {n: mean_measures([r["designs"][n] for r in per_seed]) for n in names}
    world = config.load("world")["sitesByWorld"][split]
    res = {
        "split": split, "seeds": seeds, "main": d["main"], "ablations": d["ablations"],
        "names": {n: d["designs"][n]["name"] for n in names}, "labels": {n: d["designs"][n]["label"] for n in names},
        "world": {"patientsPerSeed": world["patients"], "sites": sorted(world["sites"]), "scansPerSeed": 2 * world["patients"]},
        "designs": summary,
        "perSeed": [{"seed": r["seed"], **{n: _pick(r["designs"][n]) for n in d["main"]}} for r in per_seed],
        "extras": per_seed[0]["extras"],
        "evidenceRun": {"seed": seeds[0], "measures": per_seed[0]["designs"]["pipeline"]},
    }
    res["gates"] = check_gates(res)
    res["_lineage"] = per_seed[0].get("lineage")
    res["_lineageDigest"] = per_seed[0].get("lineageDigest")
    return res


def _pick(m: dict[str, Any]) -> dict[str, Any]:
    keys = ["usableScanShare", "suvErrorMedian", "lesionSensitivity", "recipKappa", "phiLeaks", "factPrecision", "responseAuc"]
    return {k: m[k] for k in keys}


def mean_measures(xs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in xs[0]:
        vals = [x[k] for x in xs]
        if all(isinstance(v, bool) for v in vals):
            out[k] = all(vals)
        elif all(isinstance(v, int | float) for v in vals):
            good = [float(v) for v in vals if not (isinstance(v, float) and math.isnan(v))]
            out[k] = sum(good) / len(good) if good else math.nan
        elif all(isinstance(v, str) for v in vals):
            out[k] = Counter(vals).most_common(1)[0][0]
        else:
            out[k] = sorted({str(i) for v in vals for i in (v if isinstance(v, list) else [v])})
    return out


def check_gates(res: dict[str, Any]) -> dict[str, Any]:
    g = config.load("gates")
    p = res["designs"]["pipeline"]
    c = g["pipeline"]
    rows = []

    def add(name: str, value: Any, limit: Any, kind: str) -> None:
        if kind == "max":
            ok = value <= limit
        elif kind == "min":
            ok = value >= limit
        else:
            ok = value == limit
        rows.append({"gate": name, "value": value, "limit": limit, "kind": kind, "pass": bool(ok)})

    add("Identifiers found in anything that left the pipeline", p["phiLeaks"], c["phiLeaksMax"], "max")
    add("Median SUV error per scan", p["suvErrorMedian"], c["suvErrorMedianMax"], "max")
    add("Scans with SUV more than 10% off", p["suvErrorOver10pctShare"], c["suvErrorOver10pctShareMax"], "max")
    add("Scans counted twice", p["duplicateScans"], c["duplicateScansMax"], "max")
    add("Patients with baseline and follow-up paired", p["pairedShare"], c["pairedShareMin"], "min")
    add("RECIP agreement with the reference (kappa)", p["recipKappa"], c["recipKappaMin"], "min")
    add("Invented facts kept in the knowledge graph", p["hallucinatedFactsKept"], c["hallucinatedFactsKeptMax"], "max")
    add("Typos admitted as ontology terms", p["noiseTermsInduced"], c["noiseTermsInducedMax"], "max")
    add("New terms induced (of 2 in the documents)", p["novelTermsInduced"], c["novelTermsInducedMin"], "min")
    add("PSA50 prediction AUC, leave-site-out", p["responseAuc"], c["responseAucMin"], "min")
    add("Miscalibrated site found", p["driftSiteFound"], c["driftSiteFound"], "eq")
    if g["eachSafeguardMatters"]:
        worse = []
        for n in res["ablations"]:
            a = res["designs"][n]
            hit = [k for k in LOWER if a[k] > p[k] * 1.0001 + 1e-9] + [k for k in HIGHER if float(a[k]) < float(p[k]) * 0.9999 - 1e-9]
            worse.append({"design": n, "worseOn": hit})
        share = sum(1 for x in worse if x["worseOn"]) / len(worse)
        add("Ablations worse than the pipeline on some measure (share)", share, 1.0, "min")
        rows[-1]["detail"] = worse
    return {"pipeline": rows, "pass": all(r["pass"] for r in rows)}


def reports_dir() -> Path:
    d = config.root() / "reports"
    d.mkdir(exist_ok=True)
    return d


def write(res: dict[str, Any]) -> None:
    from tep.evidence.pack import endpoints, write_pack

    lineage = res.pop("_lineage", None)
    digest = res.pop("_lineageDigest", None)
    res["lineageDigest"] = digest
    res["endpoints"] = endpoints(res["evidenceRun"]["measures"], None)
    (reports_dir() / f"{res['split']}.json").write_text(json.dumps(_round(res), indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    if lineage is not None:
        write_pack(res, lineage)


def _round(x: Any) -> Any:
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 5)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def load(split: str) -> dict[str, Any] | None:
    p = reports_dir() / f"{split}.json"
    return json.loads(p.read_text()) if p.exists() else None


def run_heldout_once() -> dict[str, Any]:
    lock = reports_dir() / "heldout.lock"
    if lock.exists():
        raise Locked("reports/heldout.lock exists: the held-out sites have been run once; add new seeds under a new name and an ADR")
    lock.write_text(json.dumps({"seeds": config.load("seeds")["heldout"], "configSha256": config.config_hash()}, indent=1) + "\n")
    res = run_split("heldout")
    write(res)
    return res


__all__ = ["SWITCHES", "run_split", "write", "load", "run_heldout_once", "Locked"]
