export type Measures = Record<string, number | boolean | string | string[] | null>;

export interface Gate { gate: string; value: number | boolean; limit: number | boolean; kind: "max" | "min" | "eq"; pass: boolean; detail?: { design: string; worseOn: string[] }[] }
export interface SiteRow {
  site: string; series: number; completeness: number; validity: number; quarantined_share: number; recovered_share: number;
  duplicate_instances: number; order_fixed_share: number; liver_reference_median: number | null;
}
export interface MipScan { visit: string; day: number; mip: number[][]; tvMl: number; suvMean: number; lesions: { x: number; z: number; region: string; suvMax: number }[] }
export interface Endpoint { id: string; text: string; estimate: number | null; ciLow: number | null; ciHigh: number | null; criterion: Record<string, number | number[]>; met: boolean; role: string }
export interface TimelineItem { type: string; code: string; date: string; value: number | null; source: string }

export interface Split {
  split: string; seeds: number[]; main: string[]; ablations: string[];
  names: Record<string, string>; labels: Record<string, string>;
  world: { patientsPerSeed: number; sites: string[]; scansPerSeed: number };
  designs: Record<string, Measures>;
  gates: { pipeline: Gate[]; pass: boolean };
  endpoints: Endpoint[];
  lineageDigest: string | null;
  evidenceRun: { seed: number; measures: Measures };
  extras: {
    mip: { patient: string; recip: string; recipTruth: string; scans: MipScan[] } | Record<string, never>;
    quality: { sites: SiteRow[]; issues: { site: string; code: string; n: number }[] };
    letters: { site: string; issues: string[]; text: string }[];
    model: { shap: Record<string, number>; coefficients: Record<string, number>; n: number; positives: number; sites: number };
    ontology: { induced: Record<string, string>; held: Record<string, { documents: number; sites: number; likelyMisspellingOf?: string }> };
    timeline: TimelineItem[];
    consistency: Record<string, number>;
    rejections: Record<string, number>;
  };
}
export interface Report { dev: Split; heldout?: Split }

export async function loadReport(): Promise<Report> {
  const res = await fetch("./data/report.json");
  if (!res.ok) throw new Error("The lab report is missing. Run `tep lab dev` to generate it.");
  return (await res.json()) as Report;
}

export const num = (m: Measures, k: string): number => {
  const v = m[k];
  return typeof v === "number" ? v : typeof v === "boolean" ? (v ? 1 : 0) : NaN;
};
