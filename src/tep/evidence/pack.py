"""The evidence pack: the analysis plan, each endpoint against its criterion, the data inventory, a model card,
the lineage behind every number, and a manifest of file hashes sealed with an HMAC.

Files are written without timestamps, so the same code, config and data give the same pack, byte for byte.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
from typing import Any

from tep import config
from tep.lineage.store import Lineage, Run

DEV_KEY = b"dev-only-evidence-key"


def _key() -> bytes:
    k = os.environ.get("TEP_EVIDENCE_KEY")
    return k.encode() if k else DEV_KEY


def _dump(obj: Any) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode()


def _met(criterion: dict[str, Any], est: float, lo: float | None = None) -> bool:
    if est is None or (isinstance(est, float) and math.isnan(est)):
        return False
    if "ciLowerAtLeast" in criterion:
        return lo is not None and lo >= criterion["ciLowerAtLeast"]
    if "atLeast" in criterion:
        return est >= criterion["atLeast"]
    if "atMost" in criterion:
        return est <= criterion["atMost"]
    if "between" in criterion:
        return criterion["between"][0] <= est <= criterion["between"][1]
    return False


def endpoints(m: dict[str, Any], model_artifact: str | None) -> list[dict[str, Any]]:
    sap = config.load("sap")["endpoints"]
    vals = {
        "lesion_sensitivity": (m["lesionSensitivity"], m["lesionSensitivityLo"], m["lesionSensitivityHi"]),
        "fp_per_scan": (m["fpPerScan"], None, None),
        "suv_error": (m["suvErrorMedian"], None, None),
        "recip_kappa": (m["recipKappa"], None, None),
        "response_auc": (m["responseAuc"], m["responseAucLo"], m["responseAucHi"]),
        "calibration_slope": (m["calibrationSlope"], None, None),
    }
    out = []
    for e in [sap["primary"], *sap["secondary"]]:
        est, lo, hi = vals[e["id"]]
        row = {"id": e["id"], "text": e["text"], "estimate": est, "ciLow": lo, "ciHigh": hi, "criterion": e["criterion"],
               "met": _met(e["criterion"], est, lo), "role": "primary" if e is sap["primary"] else "secondary"}
        if e["id"] in ("response_auc", "calibration_slope") and model_artifact:
            row["lineage"] = model_artifact
        out.append(row)
    return out


def model_card(res: dict[str, Any]) -> str:
    x = res["extras"]["model"]
    m = res["evidenceRun"]["measures"]
    feats = config.load("sap")["model"]["features"]
    lines = ["# Model card: PSA50 response from baseline PSMA-PET and PSA", "",
             "**Intended use.** Research only: to study whether baseline PSMA expression and tumour burden predict PSA50 response "
             "to [177Lu]Lu-PSMA therapy. Not for treatment decisions.", "",
             f"**Data.** {x['n']} patients with a usable baseline scan and two PSA values from the documents, {x['positives']} responders, "
             f"{x['sites']} sites. Simulated cohort (see README, Limits).", "",
             "**Model.** Logistic regression on standardised features, fixed in the analysis plan before validation: " + ", ".join(feats) + ".", "",
             f"**Validation.** Leave-one-site-out. AUC {m['responseAuc']:.3f} (95% CI {m['responseAucLo']:.3f}-{m['responseAucHi']:.3f}, DeLong); "
             f"calibration slope {m['calibrationSlope']:.2f}; Brier {m['brier']:.3f}. Gradient boosting as a secondary analysis: AUC {m['gbAuc']:.3f}. "
             f"The same cohort's true response probabilities reach AUC {m['oracleAuc']:.3f}: the ceiling for this data.", "",
             "**Explanation (mean |SHAP| on the standardised scale).**", "", "| Feature | Mean abs SHAP | Coefficient |", "|---|---:|---:|"]
    for f in sorted(x["shap"], key=x["shap"].get, reverse=True):
        lines.append(f"| {f} | {x['shap'][f]:.3f} | {x['coefficients'][f]:+.3f} |")
    lines += ["", "**Limits.** Synthetic patients; 5 features; no external validation; sites differ in tracer and protocol only as simulated."]
    return "\n".join(lines) + "\n"


def write_pack(res: dict[str, Any], lineage: dict[str, Any]) -> Path:
    out = config.root() / "evidence" / res["split"]
    out.mkdir(parents=True, exist_ok=True)
    lin = Lineage(lineage["codeVersion"], lineage["configHash"])
    lin.artifacts = lineage["artifacts"]
    for r in lineage["runs"]:
        lin.runs[r["run_id"]] = Run(**r)
        for o in r["outputs"]:
            lin.produced_by[o] = r["run_id"]
    model_art = next((o for r in lineage["runs"] if r["step"] == "response_model" for o in r["outputs"]), None)
    trace = lin.trace(model_art) if model_art else []
    files: dict[str, bytes] = {
        "sap.json": _dump(config.load("sap")),
        "endpoints.json": _dump(endpoints(res["evidenceRun"]["measures"], model_art)),
        "data_inventory.json": _dump(res["extras"]["quality"]),
        "model_card.md": model_card(res).encode(),
        "trace_response_model.json": _dump({"artifact": model_art, "steps": sorted({t.get("step", "source") for t in trace}),
                                            "sourceFiles": sum(1 for t in trace if t.get("source")),
                                            "chain": [t for t in trace if not t.get("source")][:12]}),
    }
    # One line per step and per artifact: byte-identical on any machine (compressed output would depend on zlib),
    # and a change shows up as a readable diff.
    lines = [json.dumps({"codeVersion": lineage["codeVersion"], "configHash": lineage["configHash"]}, sort_keys=True)]
    lines += [json.dumps({"run": r}, sort_keys=True, separators=(",", ":")) for r in lineage["runs"]]
    lines += [json.dumps({"artifact": k, **v}, sort_keys=True, separators=(",", ":")) for k, v in sorted(lineage["artifacts"].items())]
    files["lineage.jsonl"] = ("\n".join(lines) + "\n").encode()
    for name, data in files.items():
        (out / name).write_bytes(data)
    manifest = {"split": res["split"], "seed": res["evidenceRun"]["seed"], "configSha256": lineage["configHash"],
                "codeVersion": "see lineage", "files": {n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())}}
    body = _dump(manifest)
    seal = hmac.new(_key(), body, hashlib.sha256).hexdigest()
    (out / "manifest.json").write_bytes(_dump({**manifest, "hmacSha256": seal}))
    return out


def verify(split: str) -> list[str]:
    """Problems with an evidence pack: a changed file or a broken seal. Empty means intact."""
    out = config.root() / "evidence" / split
    m = json.loads((out / "manifest.json").read_text())
    seal = m.pop("hmacSha256")
    problems = []
    if not hmac.compare_digest(seal, hmac.new(_key(), _dump(m), hashlib.sha256).hexdigest()):
        problems.append("manifest seal does not match")
    for name, digest in m["files"].items():
        p = out / name
        if not p.exists():
            problems.append(f"{name} missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            problems.append(f"{name} changed")
    return problems
