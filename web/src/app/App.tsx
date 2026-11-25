import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { useState } from "react";
import { Evidence } from "../features/evidence/Evidence";
import { Knowledge } from "../features/knowledge/Knowledge";
import { Overview } from "../features/overview/Overview";
import { Sites } from "../features/sites/Sites";
import { loadReport, type Report } from "../shared/data/report";
import { useLoad } from "../shared/data/useLoad";
import { StateView } from "../shared/ui/StateView";
import s from "./App.module.css";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "sites", label: "Sites and queries" },
  { id: "knowledge", label: "Knowledge graph" },
  { id: "evidence", label: "Evidence" },
] as const;
type Tab = (typeof TABS)[number]["id"];

function Body({ report }: { report: Report }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [split, setSplit] = useState<"dev" | "heldout">(report.heldout ? "heldout" : "dev");
  const r = split === "heldout" && report.heldout ? report.heldout : report.dev;
  return (
    <>
      <div className={s.controls}>
        <nav className={s.tabs} aria-label="Views">
          {TABS.map((t) => (
            <button key={t.id} aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        {report.heldout ? (
          <div role="group" aria-label="Sites" className={s.split}>
            <button aria-pressed={split === "heldout"} onClick={() => setSplit("heldout")}>Held-out sites (run once)</button>
            <button aria-pressed={split === "dev"} onClick={() => setSplit("dev")}>Dev sites</button>
          </div>
        ) : null}
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={`${tab}-${split}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
          {tab === "overview" && <Overview r={r} />}
          {tab === "sites" && <Sites r={r} />}
          {tab === "knowledge" && <Knowledge r={r} />}
          {tab === "evidence" && <Evidence r={r} />}
        </motion.div>
      </AnimatePresence>
    </>
  );
}

export function App() {
  const report = useLoad(loadReport);
  return (
    <MotionConfig reducedMotion="user">
      <div className={s.shell}>
        <header className={s.bar}>
          <h1 className={s.brand}>Theranostics evidence</h1>
          <p className={s.sub}>PSMA-PET/CT from site drop to audit-ready evidence</p>
        </header>
        <main className={s.main}>
          <StateView value={report}>{(data) => <Body report={data} />}</StateView>
        </main>
      </div>
    </MotionConfig>
  );
}
