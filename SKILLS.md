# Repeatable tasks

## Add a plausibility rule
1. Add the range or check to `config/rules.json` and to `tep.ingest.rules.check`, with a blocking `Issue` and a message that names the fix.
2. Add the fix text in both languages to `tep.agent.site_queries.FIX`.
3. If the site's answer supplies a value, add it to `Corrections` and to `tep.world.dicom_out.true_value`.
4. Add a defect to the world (`DEFECTS`, a site's `defects` in `config/world.json`) and a test that the rule catches it.

## Add a safeguard and prove it matters
1. Add a switch name to `SWITCHES` in `tep.lab.process` and honour it in `run`.
2. Add an ablation in `config/designs.json` with `off: [switch]`.
3. `tep lab dev`: the "each safeguard matters" gate fails if switching it off changes nothing measured.

## Add a vocabulary term
Edit `config/vocab.json` (code, kind, English and German synonyms). Terms seen in documents but not in the
vocabulary are induced by the rule in `config/vocab.json` → `induction`; do not add induced terms by hand.

## Change the analysis plan
Edit `config/sap.json` only before running held-out data. Record why in an ADR.

## Regenerate reports and the evidence pack
`tep lab dev` (never edit `REPORT.md`, the README block, `web/public/data/report.json` or `evidence/` by hand);
then `tep evidence verify dev`.

## Process real data
`tep ingest DROP OUT` with `TEP_DEID_KEY` set to a secret from your key store. The drop folder holds one folder per
site, each with one folder per series.

## Refresh the dashboard screenshots
`cd web && npm run dev`, then capture the overview, sites, knowledge and evidence views into `docs/screenshots/`.
