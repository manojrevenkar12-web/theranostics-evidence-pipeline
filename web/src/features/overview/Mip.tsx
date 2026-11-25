import { motion } from "framer-motion";
import type { MipScan } from "../../shared/data/report";
import s from "./Mip.module.css";

const WINDOW = 10; // SUV display window 0-10, inverted grey, as PSMA-PET is usually read

/** Coronal maximum-intensity projection: patient's right on the left, head at the top. */
export function Mip({ scan, label }: { scan: MipScan; label: string }) {
  const rows = scan.mip.length; // z
  const cols = scan.mip[0]?.length ?? 0; // x
  const cells = [];
  for (let z = 0; z < rows; z++) {
    for (let x = 0; x < cols; x++) {
      const v = scan.mip[z]![x]!;
      if (v < 0.4) continue;
      const g = Math.round(255 * (1 - Math.min(v / WINDOW, 1)));
      cells.push(<rect key={`${z}-${x}`} x={x} y={rows - 1 - z} width={1} height={1} fill={`rgb(${g},${g},${g})`} />);
    }
  }
  return (
    <figure className={s.figure}>
      <svg viewBox={`0 0 ${cols} ${rows}`} className={s.svg} role="img" aria-label={`${label}: maximum-intensity projection with ${scan.lesions.length} lesions marked`} shapeRendering="crispEdges">
        <rect x={0} y={0} width={cols} height={rows} className={s.bg} />
        {cells}
        {scan.lesions.map((l, i) => (
          <motion.circle key={i} cx={l.x + 0.5} cy={rows - 1 - l.z + 0.5} r={1.9} className={s.marker}
            initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.35 + i * 0.04, duration: 0.25 }}>
            <title>{`${l.region}, SUVmax ${l.suvMax}`}</title>
          </motion.circle>
        ))}
      </svg>
      <figcaption className={s.caption}>
        <span className={s.visit}>{label}</span>
        <span>PSMA-TV {scan.tvMl.toFixed(1)} mL, SUVmean {scan.suvMean.toFixed(1)}, {scan.lesions.length} lesions</span>
      </figcaption>
    </figure>
  );
}
