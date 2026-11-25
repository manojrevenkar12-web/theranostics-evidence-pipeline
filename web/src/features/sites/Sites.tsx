import type { Split } from "../../shared/data/report";
import { Empty } from "../../shared/ui/StateView";
import { fix, int, pct } from "../../shared/ui/format";
import s from "./Sites.module.css";

export function Sites({ r }: { r: Split }) {
  const q = r.extras.quality;
  const flagged = new Set((r.evidenceRun.measures["driftSitesFlagged"] as string[] | undefined) ?? []);
  const issues = new Map<string, { code: string; n: number }[]>();
  for (const i of q.issues) issues.set(i.site, [...(issues.get(i.site) ?? []), { code: i.code, n: i.n }]);
  return (
    <div className={s.view}>
      <section aria-labelledby="q-title">
        <h2 id="q-title" className={s.h2}>Data quality by site</h2>
        <p className={s.lede}>One run (seed {r.evidenceRun.seed}). The liver reference is the median SUV in the liver across a site's scans; a site that differs from the rest by more than 8% is asked for its phantom calibration.</p>
        {q.sites.length === 0 ? <Empty>No series were received.</Empty> : (
          <table className={s.table}>
            <thead>
              <tr>
                <th scope="col">Site</th><th scope="col" className={s.num}>Series</th><th scope="col" className={s.num}>Complete</th>
                <th scope="col" className={s.num}>Passed rules</th><th scope="col" className={s.num}>Recovered by query</th>
                <th scope="col" className={s.num}>Still refused</th><th scope="col" className={s.num}>Re-sent instances</th>
                <th scope="col" className={s.num}>Liver reference</th><th scope="col">Issues found</th>
              </tr>
            </thead>
            <tbody>
              {q.sites.map((x) => (
                <tr key={x.site}>
                  <th scope="row">{x.site}</th>
                  <td className={s.num}>{int(x.series)}</td>
                  <td className={s.num}>{pct(x.completeness, 0)}</td>
                  <td className={s.num}>{pct(x.validity, 0)}</td>
                  <td className={s.num}>{pct(x.recovered_share, 0)}</td>
                  <td className={s.num}>{pct(x.quarantined_share, 0)}</td>
                  <td className={s.num}>{int(x.duplicate_instances)}</td>
                  <td className={`${s.num} ${flagged.has(x.site) ? s.flag : ""}`}>
                    {x.liver_reference_median == null ? "–" : fix(x.liver_reference_median, 2)}{flagged.has(x.site) ? " (flagged)" : ""}
                  </td>
                  <td className={s.issues}>{(issues.get(x.site) ?? []).map((i) => `${i.code} ${i.n}`).join(", ") || "none"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section aria-labelledby="l-title">
        <h2 id="l-title" className={s.h2}>Data queries sent to sites</h2>
        <p className={s.lede}>Written in the site's language, naming the series by the site's own accession number. A letter that would carry a name, ID or birth date is not sent.</p>
        {r.extras.letters.length === 0 ? <Empty>No queries were needed in this run.</Empty> : (
          <div className={s.letters}>
            {r.extras.letters.map((l, i) => (
              <article key={i} className={s.letter} aria-label={`Query to ${l.site}`}>
                <header className={s.letterHead}>To {l.site}: {l.issues.join(", ")}</header>
                <pre className={s.pre}>{l.text}</pre>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
