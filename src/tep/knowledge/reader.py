"""The reader proposes facts from a document; it never decides what is true.

SimulatedReader stands in for a language model in the lab: it reads the de-identified text and makes the
mistakes a model makes, at configured rates (misses, wrong codes, wrong numbers, invented sentences, new terms).
ClaudeReader asks a real model for the same JSON; validation treats both the same way.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from tep import config
from tep.rng import keyed
from tep.world.documents import NOVEL, Document

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}\.\d{2}\.\d{4}\b|\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\b")


@dataclass(frozen=True)
class Proposal:
    doc_id: str
    kind: str
    code: str | None
    label: str
    date: str
    value: float | None
    span: str


class Reader(Protocol):
    def read(self, doc_id: str, text: str) -> list[Proposal]: ...


def code_of(kind: str, term: str) -> str | None:
    v = config.load("vocab")
    if kind == "finding":
        return v["regionOf"].get(term)
    if kind == "scan":
        return v["tracerOf"].get(term)
    if kind == "therapy":
        return v["agentOf"].get(term)
    if kind == "psa":
        return "LAB:PSA"
    return None


class SimulatedReader:
    """Reads de-identified text with the truth's help, then errs at the configured rates (keyed, same for every design)."""

    def __init__(self, seed: int, truth: dict[str, Document]):
        self.seed = seed
        self.truth = truth
        self.cfg = config.load("world")["reader"]

    def read(self, doc_id: str, text: str) -> list[Proposal]:
        doc = self.truth[doc_id]
        lines = text.splitlines()
        orig = doc.text.splitlines()
        rng = keyed(self.seed, "reader", doc_id)
        out: list[Proposal] = []
        codes = [c for c, x in config.load("vocab")["codes"].items() if x["kind"] == "region"]
        for f in doc.facts:
            if rng.random() < self.cfg["missShare"]:
                continue
            idx = orig.index(f.span)
            span = lines[idx]
            m = DATE.search(span)
            date = m.group(0) if m else ""
            code = code_of(f.kind, f.term)
            label = f.term
            if code is None and f.term in NOVEL:
                if rng.random() > self.cfg["novelProposeShare"]:
                    continue
                label = next((x for x in NOVEL[f.term][1] if x in span), f.term)
            value = f.value
            if code and f.kind == "finding" and rng.random() < self.cfg["wrongCodeShare"]:
                code = str(rng.choice([c for c in codes if c != code]))
            if value is not None and rng.random() < self.cfg["valueErrorShare"]:
                value = round(value * 10, 2)
            out.append(Proposal(doc_id, f.kind, code, label, date, value, span))
        for typo in doc.noise_terms:
            if rng.random() < self.cfg["noiseProposeShare"]:
                span = next((ln for ln in lines if f" {typo} " in ln), "")
                m = DATE.search(span)
                out.append(Proposal(doc_id, "finding", None, typo, m.group(0) if m else "", None, span))
        if rng.random() < self.cfg["hallucinationShare"] * 3:
            m = DATE.search(text)
            date = m.group(0) if m else ""
            suv = round(float(rng.uniform(6, 30)), 1)
            span = f"PSMA-avid hepatic lesion (SUVmax {suv}) on {date}."
            out.append(Proposal(doc_id, "finding", "REG:LIVER", "liver", date, suv, span))
        return out


PROMPT = """Extract every clinical fact from this de-identified PSMA-PET or therapy document.
Return JSON: {"facts": [{"kind": "scan|finding|therapy|psa|score", "code": "<code from the list or null>",
"label": "<term as written>", "date": "<date exactly as written>", "value": <number or null>,
"span": "<the exact sentence that states it, copied verbatim>"}]}
Codes: CODES
Use null for a term not in the list. Copy spans exactly; do not paraphrase.

Document:
"""


class ClaudeReader:
    """A real model behind the same interface. Its output goes through the same validation as the simulator's."""

    def __init__(self, client: Any, model: str = "claude-sonnet-4-5"):
        self.client = client
        self.model = model

    def read(self, doc_id: str, text: str) -> list[Proposal]:
        codes = ", ".join(config.load("vocab")["codes"])
        msg = self.client.messages.create(model=self.model, max_tokens=2000,
                                          messages=[{"role": "user", "content": PROMPT.replace("CODES", codes) + text}])
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        return parse(doc_id, raw)


def parse(doc_id: str, raw: str) -> list[Proposal]:
    try:
        start = raw.index("{")
        data = json.loads(raw[start: raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    out = []
    for f in data.get("facts", []):
        try:
            v = f.get("value")
            out.append(Proposal(doc_id, str(f["kind"]), f.get("code"), str(f.get("label", "")), str(f.get("date", "")),
                                None if v is None else float(v), str(f.get("span", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def as_dict(p: Proposal) -> dict[str, Any]:
    return asdict(p)
