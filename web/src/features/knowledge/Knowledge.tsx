import { motion } from "framer-motion";
import type { Split } from "../../shared/data/report";
import { Empty } from "../../shared/ui/StateView";
import { fix } from "../../shared/ui/format";
import s from "./Knowledge.module.css";

const KIND: Record<string, string> = { scan: "Scan", finding: "Reported finding", imaging_finding: "Imaged finding", therapy: "Therapy cycle", psa: "PSA", score: "Score" };

export function Knowledge({ r }: { r: Split }) {
  const rej = Object.entries(r.extras.rejections).sort((a, b) => b[1] - a[1]);
  const top = Math.max(1, ...rej.map(([, n]) => n));
  const induced = Object.entries(r.extras.ontology.induced);
  const held = Object.entries(r.extras.ontology.held);
  const m = r.evidenceRun.measures;
  return (
    <div className={s.view}>
      <section aria-labelledby="k-title" className={s.intro}>
        <h2 id="k-title" className={s.h2}>Facts from reports and letters, checked by code</h2>
        <p className={s.lede}>
          The reader proposed facts from {r.world.patientsPerSeed * 4} English and German documents. Code kept {fix(Number(m["factsKept"]), 0)} of them;
          {" "}{fix(Number(m["factPrecision"]) * 100, 1)}% of those are correct and none was invented.
        </p>
      </section>
      <div className={s.cols}>
        <section aria-labelledby="r-title">
          <h3 id="r-title" className={s.h3}>Why proposals were refused</h3>
          {rej.length === 0 ? <Empty>Nothing was refused.</Empty> : (
            <ul className={s.bars}>
              {rej.map(([reason, n], i) => (
                <li key={reason}>
                  <span className={s.barLabel}>{reason}</span>
                  <span className={s.track}>
                    <motion.span className={s.bar} initial={{ width: 0 }} animate={{ width: `${(n / top) * 100}%` }} transition={{ delay: i * 0.05, duration: 0.4 }} />
                  </span>
                  <span className={s.barValue}>{n}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="o-title">
          <h3 id="o-title" className={s.h3}>Ontology: terms the vocabulary did not have</h3>
          {induced.length === 0 ? <Empty>No term reached 3 documents from 2 sites.</Empty> : (
            <ul className={s.terms}>{induced.map(([k, code]) => <li key={k}><strong>{k}</strong> added as <code className={s.code}>{code}</code></li>)}</ul>
          )}
          <h4 className={s.h4}>Held for review</h4>
          {held.length === 0 ? <Empty>None.</Empty> : (
            <ul className={s.terms}>
              {held.slice(0, 8).map(([k, v]) => (
                <li key={k}>{k}: {v.documents} document{v.documents === 1 ? "" : "s"}, {v.sites} site{v.sites === 1 ? "" : "s"}{v.likelyMisspellingOf ? `, likely a misspelling of "${v.likelyMisspellingOf}"` : ""}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <section aria-labelledby="t-title">
        <h3 id="t-title" className={s.h3}>One patient on the knowledge graph's time axis (dates shifted)</h3>
        {r.extras.timeline.length === 0 ? <Empty>No facts for this patient.</Empty> : (
          <ol className={s.timeline}>
            {r.extras.timeline.map((t, i) => (
              <li key={i} className={s.event}>
                <span className={s.date}>{t.date}</span>
                <span className={s.kind}>{KIND[t.type] ?? t.type}</span>
                <span>{t.code}{t.value != null ? `, ${t.value}` : ""}</span>
                <span className={s.src}>{t.source.split("#")[0]}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
