"""tep: lab dev | lab heldout | lab report | lab gate [split] | evidence verify [split] | ingest DROP OUT"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lab = sub.add_parser("lab")
    lab.add_argument("action", choices=["dev", "heldout", "report", "gate"])
    lab.add_argument("split", nargs="?", default="dev")
    ev = sub.add_parser("evidence")
    ev.add_argument("action", choices=["verify"])
    ev.add_argument("split", nargs="?", default="dev")
    ing = sub.add_parser("ingest")
    ing.add_argument("drop", type=Path)
    ing.add_argument("out", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "lab":
        from tep.lab import report, study

        if a.action == "dev":
            study.write(study.run_split("dev"))
            report.write_all()
        elif a.action == "heldout":
            try:
                study.run_heldout_once()
            except study.Locked as e:
                print(e, file=sys.stderr)
                return 3
            report.write_all()
        elif a.action == "report":
            report.write_all()
        else:
            r = study.load(a.split)
            if r is None:
                print(f"reports/{a.split}.json is missing", file=sys.stderr)
                return 1
            for g in r["gates"]["pipeline"]:
                print(("PASS" if g["pass"] else "FAIL"), g["gate"], g["value"], g["kind"], g["limit"])
            return 0 if r["gates"]["pass"] else 1
        return 0
    if a.cmd == "evidence":
        from tep.evidence.pack import verify

        problems = verify(a.split)
        print(json.dumps({"split": a.split, "intact": not problems, "problems": problems}))
        return 0 if not problems else 1
    if a.cmd == "ingest":
        from tep.ingest.run import ingest

        summary = ingest(a.drop, a.out)
        print(json.dumps(summary, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
