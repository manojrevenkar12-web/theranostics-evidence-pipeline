"""A temporal knowledge graph per patient: scans, findings, therapy cycles, PSA and scores on a time axis,
each fact carrying where it came from (document and sentence hash, or the imaging step's artifact)."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class Fact:
    patient: str
    kind: str  # scan | finding | therapy | psa | score | imaging_finding
    code: str
    date: dt.date
    value: float | None
    source: str  # doc:<id>#<sentence sha> or artifact:<id>


def sentence_ref(doc_id: str, span: str) -> str:
    return f"doc:{doc_id}#{hashlib.sha256(span.encode()).hexdigest()[:12]}"


def build(facts: list[Fact]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    by_patient: dict[str, list[Fact]] = {}
    for f in facts:
        by_patient.setdefault(f.patient, []).append(f)
    for p, fs in by_patient.items():
        g.add_node(p, type="patient")
        fs = sorted(fs, key=lambda x: (x.date, x.kind, x.code))
        prev = None
        for f in fs:
            node = f"{p}|{f.kind}|{f.code}|{f.date.isoformat()}|{f.value}"
            g.add_node(node, type=f.kind, code=f.code, date=f.date.isoformat(), value=f.value, source=f.source)
            g.add_edge(p, node, rel="has")
            if prev is not None and prev != node:
                g.add_edge(prev, node, rel="before", days=(f.date - dt.date.fromisoformat(g.nodes[prev]["date"])).days)
            prev = node
    return g


def timeline(g: nx.MultiDiGraph, patient: str) -> list[dict]:
    out = [dict(g.nodes[n]) for _, n, d in g.out_edges(patient, data=True) if d.get("rel") == "has"]
    return sorted(out, key=lambda x: (x["date"], x["type"]))


def consistency(g: nx.MultiDiGraph) -> dict[str, int]:
    """Checks that need the time axis: a follow-up scan before the first therapy, findings reported but not imaged."""
    out = {"followUpBeforeTherapy": 0, "reportedNotImaged": 0, "imagedNotReported": 0, "patientsChecked": 0}
    for p in [n for n, d in g.nodes(data=True) if d.get("type") == "patient"]:
        tl = timeline(g, p)
        scans = sorted({x["date"] for x in tl if x["type"] == "scan"})
        therapy = sorted(x["date"] for x in tl if x["type"] == "therapy")
        if len(scans) >= 2 and therapy and scans[-1] < therapy[0]:
            out["followUpBeforeTherapy"] += 1
        for day in scans:
            rep = {x["code"] for x in tl if x["type"] == "finding" and x["date"] == day}
            img = {x["code"] for x in tl if x["type"] == "imaging_finding" and x["date"] == day}
            if rep or img:
                out["patientsChecked"] += 1
                out["reportedNotImaged"] += len(rep - img)
                out["imagedNotReported"] += len(img - rep)
    return out
