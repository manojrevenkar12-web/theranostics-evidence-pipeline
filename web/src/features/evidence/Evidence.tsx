import { motion } from "framer-motion";
import type { Endpoint, Split } from "../../shared/data/report";
import { num } from "../../shared/data/report";
import { Empty } from "../../shared/ui/StateView";
import { fix, int, pct } from "../../shared/ui/format";
import s from "./Evidence.module.css";

function criterion(c: Endpoint["criterion"]): string {
  if ("ciLowerAtLeast" in c) return `lower 95% bound at least ${c.ciLowerAtLeast}`;
  if ("atLeast" in c) return `at least ${c.atLeast}`;
  if ("atMost" in c) return `at most ${c.atMost}`;
  if ("between" in c) return `between ${(c.between as number[]).join(" and ")}`;
  return "";
}

export function Evidence({ r }: { r: Split }) {
  const shap = Object.entries(r.extras.model.shap).sort((a, b) => b[1] - a[1]);
  const top = Math.max(1e-9, ...shap.map(([, v]) => v));
  const detail = r.gates.pipeline.find((g) => g.detail)?.detail ?? [];
  return (
    <div className={s.view}>
      <section aria-labelledby="e-title">
        <h2 id="e-title" className={s.h2}>Endpoints against the analysis plan</h2>
        <p className={s.lede}>Fixed in <code>config/sap.json</code> before the held-out sites were run. Seed {r.evidenceRun.seed}; sealed in <code>evidence/{r.split}/manifest.json</code>.</p>
        {r.endpoints.length === 0 ? <Empty>No endpoints were computed.</Empty> : (
          <table className={s.table}>
            <thead><tr><th scope="col">Endpoint</th><th scope="col" className={s.num}>Estimate (95% CI)</th><th scope="col">Criterion</th><th scope="col">Met</th></tr></thead>
            <tbody>
              {r.endpoints.map((e) => (
                <tr key={e.id}>
                  <th scope="row">{e.role === "primary" ? <strong>Primary. </strong> : null}{e.text}</th>
                  <td className={s.num}>{fix(e.estimate ?? NaN, 3)}{e.ciLow != null && e.ciHigh != null ? ` (${fix(e.ciLow, 3)}–${fix(e.ciHigh, 3)})` : ""}</td>
                  <td>{criterion(e.criterion)}</td>
                  <td className={e.met ? s.pass : s.fail}>{e.met ? "Met" : "Not met"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <div className={s.cols}>
        <section aria-labelledby="m-title">
          <h3 id="m-title" className={s.h3}>What drives the response model (mean |SHAP|)</h3>
          <p className={s.small}>{r.extras.model.n} patients, {r.extras.model.positives} PSA50 responders, {r.extras.model.sites} sites, leave-one-site-out.</p>
          {shap.length === 0 ? <Empty>Too few patients to fit the model.</Empty> : (
            <ul className={s.bars}>
              {shap.map(([f, v], i) => (
                <li key={f}>
                  <span>{f}</span>
                  <span className={s.track}><motion.span className={s.bar} initial={{ width: 0 }} animate={{ width: `${(v / top) * 100}%` }} transition={{ delay: i * 0.06, duration: 0.4 }} /></span>
                  <span className={s.value}>{fix(v, 3)} ({r.extras.model.coefficients[f]! >= 0 ? "+" : "−"})</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="g-title">
          <h3 id="g-title" className={s.h3}>Gates, mean of {r.seeds.length} runs</h3>
          <ul className={s.gates}>
            {r.gates.pipeline.map((g) => (
              <li key={g.gate}><span className={g.pass ? s.pass : s.fail}>{g.pass ? "Pass" : "Fail"}</span>{g.gate}: {typeof g.value === "number" ? Number(g.value.toPrecision(4)) : String(g.value)}</li>
            ))}
          </ul>
        </section>
      </div>
      <section aria-labelledby="a-title">
        <h3 id="a-title" className={s.h3}>Each safeguard switched off on its own</h3>
        <table className={s.table}>
          <thead><tr><th scope="col">Switched off</th><th scope="col">Worse on</th><th scope="col" className={s.num}>Usable scans</th><th scope="col" className={s.num}>SUV &gt;10% off</th><th scope="col" className={s.num}>Leaks</th><th scope="col" className={s.num}>Invented facts</th></tr></thead>
          <tbody>
            {r.ablations.map((n) => {
              const m = r.designs[n]!;
              return (
                <tr key={n}>
                  <th scope="row" title={r.labels[n]}>{r.names[n]}</th>
                  <td>{detail.find((d) => d.design === n)?.worseOn.join(", ") || "nothing"}</td>
                  <td className={s.num}>{pct(num(m, "usableScanShare"))}</td>
                  <td className={s.num}>{pct(num(m, "suvErrorOver10pctShare"))}</td>
                  <td className={s.num}>{int(num(m, "phiLeaks"))}</td>
                  <td className={s.num}>{fix(num(m, "hallucinatedFactsKept"), 1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className={s.small}>Lineage digest of this run: <code>{r.lineageDigest ?? "not recorded"}</code></p>
      </section>
    </div>
  );
}
