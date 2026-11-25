"""Production path: a folder of site drops in, de-identified SUV volumes, sidecars, data queries and lineage out."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pandas as pd

from tep import config
from tep.agent import site_queries
from tep.features.lesions import segment
from tep.ingest import deid
from tep.ingest.rules import check, uptake_minutes
from tep.ingest.series import read_drop
from tep.ingest.suv import suv_factor
from tep.ingest.volume import affine_ras, stack, to_nifti
from tep.lab.process import code_version
from tep.lineage.store import Lineage, sha
from tep.observability.quality import site_quality


def ingest(drop: Path, out: Path, language: str = "en") -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "nifti").mkdir(exist_ok=True)
    (out / "queries").mkdir(exist_ok=True)
    lin = Lineage(code_version(), config.config_hash())
    rows, issue_rows = [], []
    accepted = refused = 0
    for s in read_drop(drop):
        h = s.header
        pseudo = deid.pseudonym(deid.linkage_key(str(h.PatientName), str(h.PatientBirthDate)))
        issues = check(s)
        blocking = [i for i in issues if i.blocking]
        for i in issues:
            issue_rows.append({"site": s.site, "code": i.code, "blocking": i.blocking})
        ref = deid.new_uid(s.series_uid)
        src = [lin.source(sha(sorted(s.sources)), "dicom-series", f"{s.site}/{ref}: {len(s.sources)} files")]
        row = {"site": s.site, "series": ref, "status": "accepted", "has_weight": "PatientWeight" in h,
               "has_dose": "RadiopharmaceuticalInformationSequence" in h, "has_times": uptake_minutes(s) is not None,
               "blocking_issues": len(blocking), "duplicate_instances": s.duplicate_instances,
               "order_fixed": any(i.code == "instanceOrder" for i in issues), "liver_reference": None}
        if blocking:
            refused += 1
            row["status"] = "quarantined"
            q = site_queries.draft(s.site, language, str(h.get("AccessionNumber", ref)), blocking)
            (out / "queries" / f"{s.site}_{ref}.txt").write_text(q.text + "\n")
            lin.step("quarantine", src, {"decision": {"series": ref, "issues": [i.code for i in blocking]}})
            rows.append(row)
            continue
        vol = stack(s)
        suv = (vol * suv_factor(s)).astype(np.float32)
        f = segment(suv)
        row["liver_reference"] = f.liver_reference
        name = f"{pseudo}_{ref[-12:]}"
        nib.save(to_nifti(suv, affine_ras(s)), out / "nifti" / f"{name}_suv.nii.gz")
        side = {"header": deid.header(h, pseudo), "suvFactor": suv_factor(s), "issues": [vars(i) for i in issues],
                "features": {"tvMl": f.tv_ml, "suvMean": f.suv_mean, "suvMax": f.suv_max, "lesions": f.lesion_count}}
        (out / "nifti" / f"{name}.json").write_text(json.dumps(side, indent=1, default=str) + "\n")
        lin.step("ingest", src, {"suv": sha(np.round(suv, 3).tobytes()), "sidecar": sha(side)})
        accepted += 1
        rows.append(row)
    quality = site_quality(pd.DataFrame(rows), pd.DataFrame(issue_rows))
    (out / "quality.json").write_text(json.dumps(quality, indent=1, default=str) + "\n")
    (out / "lineage.json").write_text(json.dumps(lin.export(), indent=1) + "\n")
    return {"accepted": accepted, "refused": refused, "lineageDigest": lin.digest(), "out": str(out)}
