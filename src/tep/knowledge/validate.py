"""Code decides which proposed facts are kept, and which new terms enter the ontology.

A fact is kept only if its sentence is in the document, its date and number are in that sentence, and its
code is one the vocabulary knows and the sentence names. A term the vocabulary does not know is held until it
has been seen in enough documents from enough sites; then it is added as an induced term.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

from tep import config
from tep.knowledge.reader import Proposal

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")


@dataclass
class Decision:
    proposal: Proposal
    accepted: bool
    reason: str
    code: str | None
    date: dt.date | None


def _edits1(a: str, b: str) -> bool:
    """True when b is one deletion, insertion, substitution or swap away from a."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


def misspelling_of(label: str) -> str | None:
    """A candidate term one edit away from a word the vocabulary already has is held as a likely misspelling."""
    words = {w for c in config.load("vocab")["codes"].values() for syn in c["synonyms"] for w in re.findall(r"[\wäöüß&-]+", syn.lower()) if len(w) >= 4}
    for tok in re.findall(r"[\wäöüß&-]+", norm(label)):
        for w in words:
            if _edits1(tok, w):
                return w
    return None


@dataclass
class Ontology:
    induced: dict[str, str] = field(default_factory=dict)  # normalised label -> NEW:code
    held: dict[str, dict] = field(default_factory=dict)


def parse_date(s: str) -> dt.date | None:
    s = s.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s)
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", s):
            d, m, y = s.split(".")
            return dt.date(int(y), int(m), int(d))
        m2 = re.fullmatch(r"(\d{1,2}) (\w{3}) (\d{4})", s)
        if m2 and m2[2] in MONTHS:
            return dt.date(int(m2[3]), MONTHS.index(m2[2]) + 1, int(m2[1]))
    except ValueError:
        return None
    return None


def numbers(span: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in NUM.findall(span)]


def norm(label: str) -> str:
    """Canonical form of a term: lower case, single spaces, isotope prefixes like [177Lu] dropped."""
    s = re.sub(r"\[\d+[a-z]+\]", "", label.strip().lower())
    return re.sub(r"\s+", " ", s).strip()


def check(p: Proposal, text: str) -> tuple[bool, str, dt.date | None]:
    vocab = config.load("vocab")["codes"]
    if not p.span or p.span not in text:
        return False, "sentence not in document", None
    d = parse_date(p.date)
    if d is None or p.date not in p.span:
        return False, "date not in sentence", None
    if p.value is not None and not any(abs(n - p.value) <= 1e-6 * max(1.0, abs(p.value)) for n in numbers(p.span)):
        return False, "number not in sentence", d
    if p.code is not None:
        c = vocab.get(p.code)
        if c is None:
            return False, "unknown code", d
        span = p.span.lower()
        if not any(s.lower() in span for s in c["synonyms"]):
            return False, "sentence does not name the coded term", d
        return True, "ok", d
    if not p.label or norm(p.label) not in norm(p.span.lower()):
        return False, "term not in sentence", d
    return True, "new term", d


def decide(proposals: list[tuple[Proposal, str, str]], strict: bool = True) -> tuple[list[Decision], Ontology]:
    """proposals: (proposal, document text, site). With strict off, every proposal is kept as proposed."""
    rules = config.load("vocab")["induction"]
    onto = Ontology()
    out: list[Decision] = []
    pending: list[Decision] = []
    support: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"docs": set(), "sites": set()})
    for p, text, site in proposals:
        if not strict:
            code = p.code if p.code is not None else "NEW:" + re.sub(r"[^a-z0-9]+", "_", norm(p.label)).strip("_")
            if p.code is None:
                onto.induced[norm(p.label)] = code
            out.append(Decision(p, True, "kept without checks", code, parse_date(p.date)))
            continue
        ok, why, d = check(p, text)
        if ok and p.code is None:
            key = norm(p.label)
            support[key]["docs"].add(p.doc_id)
            support[key]["sites"].add(site)
            pending.append(Decision(p, False, "held for review", None, d))
            continue
        out.append(Decision(p, ok, why, p.code if ok else None, d))
    for key, s in support.items():
        near = misspelling_of(key)
        if near is not None:
            onto.held[key] = {"documents": len(s["docs"]), "sites": len(s["sites"]), "likelyMisspellingOf": near}
        elif len(s["docs"]) >= rules["minDocuments"] and len(s["sites"]) >= rules["minSites"]:
            onto.induced[key] = "NEW:" + re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        else:
            onto.held[key] = {"documents": len(s["docs"]), "sites": len(s["sites"])}
    for dcs in pending:
        key = norm(dcs.proposal.label)
        if key in onto.induced:
            out.append(Decision(dcs.proposal, True, "induced term", onto.induced[key], dcs.date))
        else:
            out.append(dcs)
    return out, onto
