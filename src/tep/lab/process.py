"""Runs one design over one prepared world and scores it against the truth.

prepare() makes the world once per seed: DICOM drops written to disk and read back, re-sends the sites would
make if asked, documents. run() applies a design to that same material, so every design meets the same luck.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tep import config
from tep.agent import site_queries
from tep.features import lesions as lz
from tep.ingest import deid
from tep.ingest.rules import Issue, check, uptake_minutes
from tep.ingest.series import Series, read_drop
from tep.ingest.suv import Corrections, suv_factor
from tep.ingest.volume import stack
from tep.knowledge import graph as kg
from tep.knowledge.reader import SimulatedReader, code_of
from tep.knowledge.validate import decide, norm
from tep.lineage.store import Lineage, sha
from tep.ml.response_model import fit_evaluate
from tep.observability.quality import site_quality
from tep.stats.diagnostic import cluster_bootstrap, cohen_kappa, delong
from tep.world.cohort import Patient, Scan, cohort
from tep.world.dicom_out import SeriesTruth, mrn, site_answers, transliterate, true_value, write_scan
from tep.world.documents import NOVEL, Document, documents
from tep.world.render import lesion_mask, suv_volume

SWITCHES = ("units", "decay", "timing", "slices", "dedupe", "linkage", "calibration", "queries", "terms", "deid")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def code_version() -> str:
    """A hash of the package's source, so the same code gives the same lineage on any machine or commit."""
    import hashlib

    h = hashlib.sha256()
    pkg = Path(__file__).resolve().parents[1]
    for f in sorted(pkg.rglob("*.py")):
        h.update(str(f.relative_to(pkg)).encode())
        h.update(f.read_bytes())
    return "src-" + h.hexdigest()[:12]


@dataclass
class Prepared:
    seed: int
    split: str
    patients: list[Patient]
    docs: list[Document]
    truth_by_series: dict[str, SeriesTruth]
    scan_by_id: dict[str, tuple[Patient, Scan]]
    series_dedup: list[Series]
    series_raw: list[Series]
    resent: dict[str, Series]
    truth_suv: dict[str, np.ndarray]


def prepare(seed: int, split: str, workdir: Path) -> Prepared:
    patients = cohort(seed, split)
    drop = workdir / "drop"
    truths: dict[str, SeriesTruth] = {}
    scans: dict[str, tuple[Patient, Scan]] = {}
    for p in patients:
        for s in p.scans:
            t = write_scan(seed, split, p, s, drop)
            truths[t.series_uid] = t
            scans[s.scan_id] = (p, s)
    resend_dir = workdir / "resend"
    for t in truths.values():
        if "missingSlice" in t.defects:
            p, s = scans[t.scan_id]
            write_scan(seed, split, p, s, resend_dir, resend=True)
    resent = {x.series_uid: x for x in read_drop(resend_dir)} if resend_dir.exists() else {}
    suv = {sid: suv_volume(seed, s).astype(np.float32) for sid, (_, s) in scans.items()}
    return Prepared(seed, split, patients, documents(seed, split, patients), truths, scans,
                    read_drop(drop, True), read_drop(drop, False), resent, suv)


@dataclass
class ScanRecord:
    series_uid: str
    scan_id: str  # truth, for scoring only
    pseudo: str
    site: str
    date: str  # YYYYMMDD as received (ordering); shifted on output
    suv: np.ndarray | None = None
    excluded: bool = False
    features: lz.ScanFeatures | None = None
    artifact: str = ""


@dataclass
class Outcome:
    measures: dict[str, Any]
    extras: dict[str, Any] = field(default_factory=dict)


def _identifiers(prep: Prepared) -> list[str]:
    out: set[str] = set()
    for p in prep.patients:
        out |= {p.family, transliterate(p.family)}
        out |= {mrn(prep.seed, s, p.key) for s in {p.baseline_site, p.followup_site}}
        b = p.birth_date
        out |= {b.strftime("%Y%m%d"), b.isoformat(), b.strftime("%d.%m.%Y"), f"{b.day} {MONTHS[b.month - 1]} {b.year}"}
    return sorted(out, key=len, reverse=True)


def _leaks(records: list[str], ids: list[str]) -> int:
    pat = re.compile("|".join(r"(?<![\w])" + re.escape(i) + r"(?![\w])" for i in ids), re.IGNORECASE)
    return sum(1 for r in records if pat.search(r))


def _raw_header(s: Series) -> str:
    return " ".join(f"{e.keyword or e.tag}={e.value}" for e in s.header.iterall() if e.keyword != "PixelData")


def _expected_code(kind: str, term: str) -> str | None:
    c = code_of(kind, term)
    if c:
        return c
    if term in NOVEL:
        surface = NOVEL[term][1][-1]
        return "NEW:" + re.sub(r"[^a-z0-9]+", "_", norm(surface)).strip("_")
    return None


def run(prep: Prepared, off: set[str], lineage: Lineage | None = None) -> Outcome:
    on = {k: k not in off for k in SWITCHES}
    w = config.load("world")
    sites = w["sitesByWorld"][prep.split]["sites"]
    rules = config.load("rules")
    series = prep.series_dedup if on["dedupe"] else prep.series_raw
    ids = _identifiers(prep)

    # 1. identity: who is this series about
    pseudo_of: dict[str, str] = {}
    by_site_id: dict[tuple[str, str], str] = {}
    names: dict[str, set[str]] = defaultdict(set)
    idents: dict[str, set[str]] = defaultdict(set)
    births: dict[str, str] = {}
    for s in series:
        h = s.header
        if on["linkage"]:
            pseudo = deid.pseudonym(deid.linkage_key(str(h.PatientName), str(h.PatientBirthDate)))
        else:
            pseudo = deid.pseudonym(f"{s.site}|{h.PatientID}")
        pseudo_of[s.series_uid + (s.sources[0] if not on["dedupe"] else "")] = pseudo
        by_site_id[(s.site, str(h.PatientID))] = pseudo
        for part in str(h.PatientName).split("^"):
            names[pseudo].add(part)
        idents[pseudo].add(str(h.PatientID))
        births[pseudo] = str(h.PatientBirthDate)

    # 2. rules, queries, SUV
    letters: list[site_queries.Query] = []
    rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    records: list[ScanRecord] = []
    outputs: list[str] = []
    for s in series:
        t = prep.truth_by_series[s.series_uid]
        key = s.series_uid + (s.sources[0] if not on["dedupe"] else "")
        pseudo = pseudo_of[key]
        lang = sites[s.site]["language"]
        issues: list[Issue] = check(s, units=on["units"], timing=on["timing"], slices=on["slices"])
        blocking = [i for i in issues if i.blocking]
        status = "accepted"
        corr = Corrections()
        used = s
        if blocking:
            status = "quarantined"
            if on["queries"]:
                q = site_queries.draft(s.site, lang, str(s.header.AccessionNumber), blocking)
                if site_queries.safe(q, ids):
                    letters.append(q)
                    if all(site_answers(prep.seed, prep.split, t.scan_id, s.site, i.code) for i in blocking):
                        _, scan = prep.scan_by_id[t.scan_id]
                        codes = {i.code for i in blocking}
                        corr = Corrections(
                            weight_kg=true_value(scan, "weight", prep.split) if codes & {"weight", "weightUnits"} else None,
                            dose_bq=true_value(scan, "doseUnits", prep.split) if "doseUnits" in codes else None,
                            uptake_min=true_value(scan, "uptakeTime", prep.split) if "uptakeTime" in codes else None)
                        if "missingSlice" in codes and s.series_uid in prep.resent:
                            used = prep.resent[s.series_uid]
                        status = "recovered"
        for i in issues:
            issue_rows.append({"site": s.site, "code": i.code, "blocking": i.blocking})
        row = {"site": s.site, "series": deid.new_uid(s.series_uid), "status": status,
               "has_weight": "PatientWeight" in s.header, "has_dose": "RadiopharmaceuticalInformationSequence" in s.header,
               "has_times": uptake_minutes(s) is not None, "blocking_issues": len(blocking),
               "duplicate_instances": s.duplicate_instances,
               "order_fixed": on["slices"] and any(i.code == "instanceOrder" for i in issues), "liver_reference": None}
        outputs.append(str(deid.header(s.header, pseudo)) if on["deid"] else _raw_header(s))
        if status == "quarantined":
            rows.append(row)
            continue
        try:
            vol = stack(used, by_position=on["slices"])
            factor = suv_factor(used, corr, respect_decay_reference=on["decay"])
        except (AttributeError, KeyError, ValueError, TypeError):
            row["status"] = "failed"
            rows.append(row)
            continue
        n = int(w["grid"]["shape"][2])
        if vol.shape[2] < n:
            vol = np.concatenate([vol, np.zeros((*vol.shape[:2], n - vol.shape[2]))], axis=2)
        suv = (vol * factor).astype(np.float32)
        rec = ScanRecord(s.series_uid, t.scan_id, pseudo, s.site, str(s.header.SeriesDate), suv)
        if lineage is not None:
            src = [lineage.source(sha(sorted(used.sources)), "dicom-series", f"{s.site}/{deid.new_uid(s.series_uid)}: {len(used.sources)} files")]
            ia = lineage.step("ingest", src, {"series": {"series": deid.new_uid(s.series_uid), "issues": [i.code for i in issues],
                                                          "status": status}}, {"corrections": vars(corr)})
            ib = lineage.step("suv", [ia["series"]], {"suv": sha(np.round(suv, 3).tobytes())},
                              {"factor": round(factor, 12), "decayReference": str(used.header.DecayCorrection)})
            rec.artifact = ib["suv"]
        records.append(rec)
        rows.append(row)

    # 3. calibration: liver reference per site against the others
    flagged: list[str] = []
    excluded_sites: list[str] = []
    refs: dict[str, list[float]] = defaultdict(list)
    for r in records:
        assert r.suv is not None
        refs[r.site].append(lz.liver_reference(r.suv))
    if on["calibration"] and refs:
        pooled = statistics.median([v for vs in refs.values() for v in vs])
        cal = rules["calibration"]
        for site, vs in sorted(refs.items()):
            dev = statistics.median(vs) / pooled - 1
            if len(vs) >= cal["minScans"] and abs(dev) > cal["maxRelativeDeviation"]:
                flagged.append(site)
                answered = False
                if on["queries"]:
                    letters.append(site_queries.calibration_query(site, sites[site]["language"], dev))
                    answered = site_answers(prep.seed, prep.split, f"site-{site}", site, "calibration")
                if answered:
                    f = sites[site]["calibration"]
                    for r in records:
                        if r.site == site:
                            r.suv = (r.suv / f).astype(np.float32)
                else:
                    excluded_sites.append(site)
                    for r in records:
                        if r.site == site:
                            r.excluded = True
    for row in rows:
        site_refs = refs.get(str(row["site"]))
        row["liver_reference"] = float(statistics.median(site_refs)) if site_refs else None

    # 4. segmentation and scoring against the truth
    suv_err: list[float] = []
    det: list[tuple[float, float]] = []
    fp = 0
    scanned = 0
    for r in records:
        assert r.suv is not None
        r.features = lz.segment(r.suv)
        if lineage is not None:
            out = lineage.step("segment", [r.artifact], {"features": {"tv": round(r.features.tv_ml, 4), "suvMean": round(r.features.suv_mean, 4),
                                                                       "n": r.features.lesion_count}})
            r.artifact = out["features"]
        if r.excluded:
            continue
        truth = prep.truth_suv[r.scan_id]
        body = truth > 1.0
        ratio = float(np.median(r.suv[body] / truth[body]))
        suv_err.append(abs(ratio - 1))
        _, scan = prep.scan_by_id[r.scan_id]
        hit: set[int] = set()
        tp = 0
        for les in scan.lesions:
            got = set(np.unique(r.features.labels[lesion_mask(truth.shape, les)])) - {0}
            if got:
                tp += 1
                hit |= got
        det.append((tp, len(scan.lesions)))
        fp += sum(1 for c in r.features.components if c.mask_index not in hit)
        scanned += 1

    # 5. patients: pairing, duplicates, RECIP
    by_pseudo: dict[str, list[ScanRecord]] = defaultdict(list)
    for r in records:
        by_pseudo[r.pseudo].append(r)
    dup = sum(len(v) - len({r.scan_id for r in v}) for v in by_pseudo.values())
    pairs_truth: list[str] = []
    pairs_pipe: list[str] = []
    paired = 0
    for rs in by_pseudo.values():
        rs.sort(key=lambda x: (x.date, x.scan_id))
        if len({r.date for r in rs}) < 2 or any(r.excluded for r in (rs[0], rs[-1])):
            continue
        rb, rf = rs[0], rs[-1]
        pb, sb = prep.scan_by_id[rb.scan_id]
        pf, sf = prep.scan_by_id[rf.scan_id]
        if pb.key != pf.key or sb.visit != "baseline" or sf.visit != "followup" or rb.features is None or rf.features is None:
            continue
        paired += 1
        new = lz.new_lesions(rb.features, rf.features)
        pairs_pipe.append(lz.recip(rb.features.tv_ml, rf.features.tv_ml, new))
        pairs_truth.append(pb.recip)

    # 6. documents -> facts -> knowledge graph
    reader = SimulatedReader(prep.seed, {d.doc_id: d for d in prep.docs})
    props = []
    doc_pseudo: dict[str, str] = {}
    texts: dict[str, str] = {}
    for d in prep.docs:
        mrn_m = re.search(r"MRN (\w+)", d.text)
        found = mrn_m.group(1) if mrn_m else ""
        pseudo = by_site_id.get((d.site, found), deid.pseudonym(f"{d.site}|{found or d.doc_id}"))
        doc_pseudo[d.doc_id] = pseudo
        if on["deid"]:
            txt = deid.text(d.text, pseudo, sorted(names.get(pseudo, set())), sorted(idents.get(pseudo, set())),
                            births.get(pseudo, "19000101"))
        else:
            txt = d.text
        texts[d.doc_id] = txt
        outputs.append(txt)
        for prop in reader.read(d.doc_id, txt):
            props.append((prop, txt, d.site))
    decisions, onto = decide(props, strict=on["terms"])

    facts: list[kg.Fact] = []
    for dcs in decisions:
        if dcs.accepted and dcs.date is not None and dcs.code is not None:
            pr = dcs.proposal
            facts.append(kg.Fact(doc_pseudo[pr.doc_id], pr.kind, dcs.code, dcs.date, pr.value, kg.sentence_ref(pr.doc_id, pr.span)))
    shift = {ps: (deid.date_offset_days(ps) if on["deid"] else 0) for ps in by_pseudo}
    for pseudo, rs in by_pseudo.items():
        for r in rs:
            day = pd.Timestamp(r.date).date() + dt.timedelta(days=shift[pseudo])
            for region in sorted({c.region for c in (r.features.components if r.features else [])}):
                code = config.load("vocab")["regionOf"].get(region)
                if code:
                    facts.append(kg.Fact(pseudo, "imaging_finding", code, day, None, f"artifact:{r.artifact or r.series_uid}"))
    graph = kg.build(facts)
    consistency = kg.consistency(graph)

    # fact scoring: relative to each patient's first scan date, as the documents state it
    anchor: dict[str, dt.date] = {}
    for f in facts:
        if f.kind != "imaging_finding":
            anchor[f.patient] = min(anchor.get(f.patient, f.date), f.date)
    truth_rows = []
    for d in prep.docs:
        pat, _ = prep.scan_by_id[f"{d.patient_key}-B"]
        for tf in d.facts:
            truth_rows.append((d.doc_id, tf.kind, _expected_code(tf.kind, tf.term), (tf.date - pat.scans[0].date).days, tf.value))
    truth_set: dict[tuple, float | None] = {(r[0], r[1], r[2], r[3]): r[4] for r in truth_rows}
    correct = halluc = wrong_value = kept = 0
    for dcs in decisions:
        if not (dcs.accepted and dcs.code and dcs.date):
            continue
        kept += 1
        pr = dcs.proposal
        if pr.span not in texts[pr.doc_id]:
            halluc += 1
            continue
        a0 = anchor.get(doc_pseudo[pr.doc_id])
        rel = (dcs.date - a0).days if a0 else None
        key4 = (pr.doc_id, pr.kind, dcs.code, rel)
        if key4 not in truth_set:
            continue
        tv = truth_set[key4]
        if tv is None or (pr.value is not None and abs(pr.value - tv) <= max(0.051, 0.005 * abs(tv))):
            correct += 1
        else:
            wrong_value += 1
    novel_codes = {_expected_code("therapy", "177Lu-PSMA-I&T"), _expected_code("score", "miPSMA score")}
    induced = set(onto.induced.values())

    # 7. response model from baseline imaging + PSA from the documents
    psa: dict[str, list[tuple[Any, float]]] = defaultdict(list)
    for f in facts:
        if f.kind == "psa" and f.value is not None:
            psa[f.patient].append((f.date, f.value))
    table = []
    for pseudo, rs in by_pseudo.items():
        r0 = rs[0]
        vals = sorted(set(psa.get(pseudo, [])))
        if r0.excluded or len(vals) < 2 or r0.features is None:
            continue
        label = 1 if vals[-1][1] <= 0.5 * vals[0][1] else 0
        ft = r0.features
        table.append({"pseudo": pseudo, "site": r0.site, "suv_mean": ft.suv_mean, "log_suv_mean": math.log(max(ft.suv_mean, 1e-3)),
                      "log_tv": math.log1p(ft.tv_ml),
                      "lesion_count": ft.lesion_count, "liver_involved": float(ft.liver_involved),
                      "log_psa": math.log(max(vals[0][1], 1e-3)), "label": label, "truth_key": prep.scan_by_id[r0.scan_id][0].key})
    tdf = pd.DataFrame(table)
    model = fit_evaluate(tdf) if len(tdf) else fit_evaluate(pd.DataFrame(columns=["site", "label"]))
    truth_y = [int(p.psa50) for p in prep.patients]
    oracle = delong(truth_y, [p.p_response for p in prep.patients])[0]
    if lineage is not None and len(tdf):
        feats = [r.artifact for rs in by_pseudo.values() for r in rs[:1]]
        t_art = lineage.step("cohort_table", feats, {"table": sha(tdf.round(6).to_dict(orient="records"))})
        lineage.step("response_model", [t_art["table"]], {"auc": round(model.auc, 6)}, {"model": "logistic", "validation": "leave-site-out"})

    # 8. what left the pipeline
    for q in letters:
        outputs.append(q.text)
    leaks = _leaks(outputs, ids)

    truth_drift = sorted(s for s, x in sites.items() if abs(x["calibration"] - 1) > 1e-9)
    sens = cluster_bootstrap(det, config.load("sap")["bootstrap"], prep.seed) if det else (math.nan,) * 3
    total_scans = len(prep.scan_by_id)
    usable = {r.scan_id for r in records if not r.excluded}
    measures: dict[str, Any] = {
        "scans": total_scans,
        "usableScanShare": len(usable) / total_scans,
        "quarantinedSeries": sum(1 for r in rows if r["status"] == "quarantined"),
        "recoveredSeries": sum(1 for r in rows if r["status"] == "recovered"),
        "queriesSent": len(letters),
        "suvErrorMedian": float(np.median(suv_err)) if suv_err else math.nan,
        "suvErrorOver10pctShare": float(np.mean([e > 0.10 for e in suv_err])) if suv_err else math.nan,
        "lesionSensitivity": sens[0], "lesionSensitivityLo": sens[1], "lesionSensitivityHi": sens[2],
        "fpPerScan": fp / scanned if scanned else math.nan,
        "duplicateScans": dup,
        "pairedShare": paired / len(prep.patients),
        "recipAccuracy": float(np.mean([a == b for a, b in zip(pairs_pipe, pairs_truth, strict=True)])) if pairs_pipe else math.nan,
        "recipKappa": cohen_kappa(pairs_pipe, pairs_truth) if pairs_pipe else math.nan,
        "phiLeaks": leaks,
        "factsKept": kept,
        "factPrecision": correct / kept if kept else math.nan,
        "factRecall": correct / len(truth_rows) if truth_rows else math.nan,
        "hallucinatedFactsKept": halluc,
        "wrongValuesKept": wrong_value,
        "novelTermsInduced": len(induced & novel_codes),
        "noiseTermsInduced": len(induced - novel_codes),
        "responseAuc": model.auc, "responseAucLo": model.auc_lo, "responseAucHi": model.auc_hi,
        "calibrationSlope": model.calibration_slope, "brier": model.brier, "gbAuc": model.gb_auc,
        "modelPatients": model.n, "oracleAuc": oracle,
        "shapTop": max(model.shap_mean_abs.items(), key=lambda kv: kv[1])[0] if model.shap_mean_abs else "",
        "driftSitesFlagged": flagged, "driftSiteFound": bool(truth_drift) and set(truth_drift) <= set(flagged),
        "sitesExcluded": excluded_sites,
        "reportedNotImaged": consistency["reportedNotImaged"], "imagedNotReported": consistency["imagedNotReported"],
    }
    mip: dict[str, Any] = {}
    candidates = [(len(rs[0].features.components), ps) for ps, rs in by_pseudo.items()
                  if rs[0].features and rs[-1].features and len({r.date for r in rs}) >= 2 and not rs[0].excluded and not rs[-1].excluded]
    if candidates:
        _, ps = max(candidates)
        rb, rf = by_pseudo[ps][0], by_pseudo[ps][-1]
        if rb.features and rf.features and rb.suv is not None and rf.suv is not None:
            new = lz.new_lesions(rb.features, rf.features)
            mip = {"patient": ps, "recip": lz.recip(rb.features.tv_ml, rf.features.tv_ml, new),
                   "recipTruth": prep.scan_by_id[rb.scan_id][0].recip,
                   "scans": [{"visit": v, "day": (pd.Timestamp(r.date) - pd.Timestamp(rb.date)).days,
                              "mip": np.round(r.suv.max(axis=1), 1).T.tolist(),
                              "tvMl": round(r.features.tv_ml, 2), "suvMean": round(r.features.suv_mean, 2),
                              "lesions": [{"x": round(c.centroid[0], 1), "z": round(c.centroid[2], 1), "region": c.region,
                                           "suvMax": round(c.suv_max, 1)} for c in r.features.components]}
                             for v, r in (("baseline", rb), ("follow-up", rf)) if r.features is not None and r.suv is not None]}
    extras = {
        "mip": mip,
        "quality": site_quality(pd.DataFrame(rows), pd.DataFrame(issue_rows)),
        "letters": [{"site": q.site, "issues": list(q.issues), "text": q.text} for q in letters[:6]],
        "model": {"shap": model.shap_mean_abs, "coefficients": model.coefficients, "n": model.n, "positives": model.positives,
                  "sites": model.sites},
        "ontology": {"induced": dict(sorted(onto.induced.items())), "held": dict(sorted(onto.held.items()))},
        "timeline": kg.timeline(graph, sorted(by_pseudo)[0]) if by_pseudo else [],
        "consistency": consistency,
        "rejections": dict(sorted(_count([d.reason for d in decisions if not d.accepted]).items())),
    }
    return Outcome(measures, extras)


def _count(xs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out
