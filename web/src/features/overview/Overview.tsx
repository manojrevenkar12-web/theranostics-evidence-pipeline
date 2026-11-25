import type { Split } from "../../shared/data/report";
import { num } from "../../shared/data/report";
import { Empty } from "../../shared/ui/StateView";
import { fix, int, pct } from "../../shared/ui/format";
import { Mip } from "./Mip";
import s from "./Overview.module.css";

const ROWS: { label: string; key: string; f: (v: number) => string; better: "lower" | "higher" }[] = [
  { label: "Scans with SUV more than 10% off", key: "suvErrorOver10pctShare", f: (v) => pct(v), better: "lower" },
  { label: "Patients with baseline and follow-up paired", key: "pairedShare", f: (v) => pct(v), better: "higher" },
  { label: "RECIP agreement with the reference (kappa)", key: "recipKappa", f: (v) => fix(v), better: "higher" },
  { label: "Records leaving with a name, ID or birth date", key: "phiLeaks", f: int, better: "lower" },
  { label: "Invented facts kept from documents", key: "hallucinatedFactsKept", f: (v) => fix(v, 1), better: "lower" },
  { label: "PSA50 prediction AUC, leave-site-out", key: "responseAuc", f: (v) => fix(v, 3), better: "higher" },
];

export function Overview({ r }: { r: Split }) {
  const mip = r.extras.mip;
  const [a, p] = [r.designs[r.main[0]!]!, r.designs[r.main[1]!]!];
  return (
    <div className={s.view}>
      <section className={s.hero} aria-labelledby="hero-title">
        <div className={s.copy}>
          <h2 id="hero-title" className={s.title}>Every number here can be traced back to the DICOM it came from</h2>
          <p className={s.lede}>
            {r.world.sites.length} sites send {r.world.scansPerSeed} PSMA-PET series per run, with the errors real sites make:
            weights in grams, doses in MBq, reversed slices, a miscalibrated scanner, names in free-text tags.
            The pipeline refuses what it cannot trust, asks the site, and measures what is left.
          </p>
          {"scans" in mip && mip.scans.length === 2 ? (
            <p className={s.verdict}>
              RECIP 1.0 from the segmentation: <strong>{mip.recip}</strong> (reference: {mip.recipTruth}), follow-up on day {mip.scans[1]!.day}.
            </p>
          ) : null}
        </div>
        {"scans" in mip && mip.scans.length === 2 ? (
          <div className={s.pair}>
            <Mip scan={mip.scans[0]!} label="Baseline" />
            <span className={s.arrow} aria-hidden>→</span>
            <Mip scan={mip.scans[1]!} label={`Follow-up, day ${mip.scans[1]!.day}`} />
          </div>
        ) : (
          <Empty>No patient with two usable scans in this run.</Empty>
        )}
      </section>
      <section aria-labelledby="cmp-title">
        <h2 id="cmp-title" className={s.h2}>Same data, two ways to handle it</h2>
        <table className={s.table}>
          <thead><tr><th scope="col">Mean of {r.seeds.length} runs</th><th scope="col" className={s.num}>{r.names[r.main[0]!]}</th><th scope="col" className={s.num}>{r.names[r.main[1]!]}</th></tr></thead>
          <tbody>
            {ROWS.map((row) => {
              const va = num(a, row.key), vp = num(p, row.key);
              return (
                <tr key={row.key}>
                  <th scope="row">{row.label}</th>
                  <td className={s.num}>{row.f(va)}</td>
                  <td className={`${s.num} ${s.strong}`}>{row.f(vp)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className={s.note}>{r.labels[r.main[0]!]}.</p>
      </section>
    </div>
  );
}
