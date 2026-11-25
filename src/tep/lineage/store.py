"""Content-addressed lineage: every artifact is named by the hash of what it is, every step records what it read.

Any number in a report can be traced back through the steps that made it to its source series. A series is named
by the hash over its files' SHA-256 hashes, so the files can be checked against it without storing every hash here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha(obj: Any) -> str:
    if isinstance(obj, bytes):
        return hashlib.sha256(obj).hexdigest()
    return hashlib.sha256(canonical(obj)).hexdigest()


@dataclass
class Run:
    run_id: str
    step: str
    inputs: list[str]
    outputs: list[str]
    params: dict[str, Any]


@dataclass
class Lineage:
    code_version: str
    config_hash: str
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    runs: dict[str, Run] = field(default_factory=dict)
    produced_by: dict[str, str] = field(default_factory=dict)

    def source(self, digest: str, kind: str, label: str) -> str:
        self.artifacts.setdefault(digest, {"kind": kind, "label": label})
        return digest

    def step(self, step: str, inputs: list[str], outputs: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, str]:
        """Records one step. outputs maps a label to the content it produced; returns label -> artifact id."""
        params = params or {}
        ids = {label: sha({"step": step, "label": label, "content": content}) for label, content in outputs.items()}
        run_id = sha({"step": step, "inputs": sorted(inputs), "outputs": sorted(ids.values()), "params": params,
                      "code": self.code_version, "config": self.config_hash})[:16]
        self.runs[run_id] = Run(run_id, step, sorted(inputs), sorted(ids.values()), params)
        for label, aid in ids.items():
            self.artifacts[aid] = {"kind": step, "label": label}
            self.produced_by[aid] = run_id
        return ids

    def trace(self, artifact: str, depth: int = 64) -> list[dict[str, Any]]:
        """The chain of steps behind an artifact, ending at source files."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        frontier = [artifact]
        while frontier and depth > 0:
            depth -= 1
            nxt: list[str] = []
            for a in frontier:
                if a in seen:
                    continue
                seen.add(a)
                run_id = self.produced_by.get(a)
                if run_id is None:
                    out.append({"artifact": a, **self.artifacts.get(a, {"kind": "unknown"}), "source": True})
                    continue
                r = self.runs[run_id]
                out.append({"artifact": a, **self.artifacts[a], "run": run_id, "step": r.step, "params": r.params, "inputs": r.inputs})
                nxt.extend(r.inputs)
            frontier = nxt
        return out

    def sources_of(self, artifact: str) -> list[str]:
        return sorted(x["artifact"] for x in self.trace(artifact) if x.get("source"))

    def digest(self) -> str:
        return sha({"runs": {k: vars(v) for k, v in sorted(self.runs.items())}})

    def export(self) -> dict[str, Any]:
        return {"codeVersion": self.code_version, "configHash": self.config_hash,
                "runs": [vars(r) for _, r in sorted(self.runs.items())],
                "artifacts": dict(sorted(self.artifacts.items()))}
