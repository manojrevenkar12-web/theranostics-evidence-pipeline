# Working on this repository

## Fast feedback

```bash
pytest -q                 # about 1 minute: unit tests and a small end-to-end world
ruff check src tests && mypy src
tep lab dev && tep lab gate dev     # about 6 minutes on 2 cores
tep evidence verify dev
cd web && npm test && npm run typecheck
```

## Invariants

1. **The truth stays in the world.** Lesions, true SUV, response, and each site's defects live in `src/tep/world`.
   The pipeline only sees files and documents, as it would at a real site.
2. **The world does not read the pipeline's settings.** `tep.world` never imports `tep.ingest`, `tep.features`,
   `tep.knowledge` or `config/designs.json`.
3. **Same luck for every design.** Every random draw is keyed by seed and identity (`tep.rng`), never by what a
   design did. Site answers to queries are drawn the same way, so a design that asks gets the same answer any design would.
4. **Refuse, do not guess.** A value outside its plausible range blocks the series and becomes a query to the site.
   No rule rescales a weight or a dose on its own.
5. **The model reads and code decides.** A reader may propose any fact; a fact is kept only when code finds its
   sentence, date, number and term in the document. New terms enter the ontology only by the induction rule.
6. **Nothing identifying leaves.** Headers leave through an allowlist; documents through scrubbing and date shifts;
   letters are checked before they are sent. The lab counts every leak.
7. **Every number traces back.** Steps record their inputs and outputs by content hash; the evidence pack is sealed.
8. **Settings in config.** Ranges, thresholds, the analysis plan, gates and seeds live in `config/*.json`.
9. **Generated reports.** `reports/*.json`, `REPORT.md`, the README results block, `web/public/data/report.json`
   and `evidence/` are written by `tep lab`; never edit them by hand. CI regenerates them and fails on a diff.

## The held-out rule

`tep lab heldout` runs the held-out sites once and writes `reports/heldout.lock` before it starts. Do not delete
the lock, change held-out seeds or sites, or tune anything after reading held-out numbers. New held-out data needs
a new name and an ADR.
