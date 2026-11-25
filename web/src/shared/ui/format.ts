export const pct = (v: number, d = 1) => (Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : "–");
export const fix = (v: number, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : "–");
export const int = (v: number) => (Number.isFinite(v) ? Math.round(v).toLocaleString("en") : "–");
