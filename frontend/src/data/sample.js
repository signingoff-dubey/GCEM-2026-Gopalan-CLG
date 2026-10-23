// SAMPLE DATA ONLY. Shapes follow docs/ML_SPEC.md §9 artifacts (metrics.json, ranking.json, safe_windows.json)
// and docs/COMPANION_APP.md (capture result JSON) so the screens can switch to the real API without changing.
// Numbers are invented placeholders, not model output. Every screen that shows them carries a "Sample data" badge.
// Dataset facts that are public (SECOM: 1567 runs, 590 features, 104 fails, Jul to Oct 2008) are kept true.

// Seeded generator, so the sample looks the same on every load.
const rng = (seed) => () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};
const rand = rng(30);

export const DATASET = {
  name: 'SECOM',
  line: 'Semiconductor fab line (anonymised)',
  runs: 1567,
  features: 590,
  featuresKept: 444,
  droppedConstant: 116,
  droppedMissing: 30,
  missingFlags: 52,
  fails: 104,
  start: '2008-07-19',
  end: '2008-10-17',
};

// Time split 70 / 15 / 15 (ML_SPEC §4). Boundaries are dates in the sample range.
export const SPLIT = {
  train: { from: '2008-07-19', to: '2008-09-20', runs: 1096, fails: 71 },
  val: { from: '2008-09-21', to: '2008-10-04', runs: 235, fails: 17 },
  test: { from: '2008-10-05', to: '2008-10-17', runs: 236, fails: 16 },
};

// metrics.json: test window only, bootstrap 95% CIs. Never accuracy (CLAUDE.md rule 4).
export const METRICS = {
  model: 'LightGBM',
  prAuc: { value: 0.21, ci: [0.11, 0.34] },
  mcc: { value: 0.24, ci: [0.08, 0.39] },
  recallAtP: { precision: 0.3, value: 0.38, ci: [0.17, 0.6] },
  baseline: { model: 'Logistic regression', prAuc: { value: 0.14, ci: [0.07, 0.25] }, mcc: { value: 0.15, ci: [0.02, 0.3] } },
  threshold: 0.18,
  confusion: { tp: 6, fp: 14, fn: 10, tn: 206 },
  positiveRate: 16 / 236,
};

// ranking.json: SHAP mean |value| x B=50 bootstraps (ML_SPEC §5). stable = top-10 frequency >= 0.7.
export const RANKING = [
  { feature: 'F59', group: 'G3', meanRank: 1.8, rankStd: 1.1, top10: 0.98, shap: 0.142 },
  { feature: 'F103', group: 'G7', meanRank: 3.1, rankStd: 1.9, top10: 0.92, shap: 0.118 },
  { feature: 'F21', group: 'G1', meanRank: 4.4, rankStd: 2.6, top10: 0.86, shap: 0.097 },
  { feature: 'F333', group: 'G12', meanRank: 5.2, rankStd: 2.4, top10: 0.84, shap: 0.091 },
  { feature: 'F486', group: 'G15', meanRank: 6.9, rankStd: 3.8, top10: 0.74, shap: 0.078 },
  { feature: 'F129', group: 'G7', meanRank: 7.6, rankStd: 4.1, top10: 0.71, shap: 0.072 },
  { feature: 'F64', group: 'G3', meanRank: 9.3, rankStd: 6.2, top10: 0.56, shap: 0.061 },
  { feature: 'F431', group: 'G14', meanRank: 10.8, rankStd: 7.9, top10: 0.48, shap: 0.055 },
  { feature: 'F210', group: 'G9', meanRank: 12.1, rankStd: 8.5, top10: 0.39, shap: 0.049 },
  { feature: 'F511', group: 'G16', meanRank: 13.7, rankStd: 9.6, top10: 0.31, shap: 0.044 },
  { feature: 'F28', group: 'G1', meanRank: 15.2, rankStd: 10.4, top10: 0.24, shap: 0.039 },
  { feature: 'F348', group: 'G12', meanRank: 17.9, rankStd: 11.8, top10: 0.18, shap: 0.033 },
].map((r) => ({ ...r, stable: r.top10 >= 0.7 }));

// Overlap of SHAP top-10 with L1 stability selection (ML_SPEC §5.5).
export const L1_OVERLAP = { shared: 7, of: 10 };

// safe_windows.json: stable top features only. Bounds are p5..p95 of train+val values; windows sit inside them.
// rate = historical failure rate, Wilson 95% CI. modelEst = model-estimated probability after the shift (circular, labelled).
export const SAFE_WINDOWS = [
  { feature: 'F59', bound: [2.1, 9.8], median: 6.2, window: [4.9, 5.4], nIn: 214, rateIn: { value: 0.028, ci: [0.013, 0.06] }, nOut: 1117, rateOut: { value: 0.073, ci: [0.059, 0.089] }, modelEst: { before: 0.071, after: 0.049 }, testCheck: { nIn: 41, rateIn: 0.024, nOut: 195, rateOut: 0.077 } },
  { feature: 'F103', bound: [-0.042, 0.031], median: -0.004, window: [-0.012, -0.006], nIn: 188, rateIn: { value: 0.032, ci: [0.015, 0.068] }, nOut: 1143, rateOut: { value: 0.071, ci: [0.058, 0.088] }, modelEst: { before: 0.07, after: 0.052 }, testCheck: { nIn: 33, rateIn: 0.03, nOut: 203, rateOut: 0.074 } },
  { feature: 'F21', bound: [-5620, -3480], median: -4410, window: [-4720, -4560], nIn: 176, rateIn: { value: 0.034, ci: [0.016, 0.072] }, nOut: 1155, rateOut: { value: 0.07, ci: [0.057, 0.086] }, modelEst: { before: 0.069, after: 0.055 }, testCheck: { nIn: 29, rateIn: 0.034, nOut: 207, rateOut: 0.072 } },
  { feature: 'F333', bound: [0.81, 1.62], median: 1.24, window: [1.02, 1.11], nIn: 203, rateIn: { value: 0.039, ci: [0.02, 0.076] }, nOut: 1128, rateOut: { value: 0.069, ci: [0.056, 0.085] }, modelEst: { before: 0.068, after: 0.057 }, testCheck: { nIn: 38, rateIn: 0.053, nOut: 198, rateOut: 0.071 } },
  { feature: 'F486', bound: [12.4, 41.7], median: 26.9, window: [18.2, 21.6], nIn: 167, rateIn: { value: 0.042, ci: [0.02, 0.084] }, nOut: 1164, rateOut: { value: 0.068, ci: [0.055, 0.084] }, modelEst: { before: 0.067, after: 0.058 }, testCheck: { nIn: 27, rateIn: 0.037, nOut: 209, rateOut: 0.072 } },
  { feature: 'F129', bound: [0.18, 0.67], median: 0.41, window: [0.29, 0.34], nIn: 159, rateIn: { value: 0.044, ci: [0.021, 0.088] }, nOut: 1172, rateOut: { value: 0.067, ci: [0.054, 0.083] }, modelEst: { before: 0.066, after: 0.059 }, testCheck: { nIn: 25, rateIn: 0.04, nOut: 211, rateOut: 0.071 } },
];

// Expected relative reduction in fail rate (CI low / point / CI high), from the safe-window analysis (ML_SPEC §7).
export const REDUCTION = { low: 0.08, mid: 0.21, high: 0.34 };

// Daily runs and fails across the sample range, for the trend chart and the calendar.
const days = [];
for (let d = new Date(`${DATASET.start}T00:00:00`); d <= new Date(`${DATASET.end}T00:00:00`); d.setDate(d.getDate() + 1)) {
  const runs = 10 + Math.floor(rand() * 13);
  const fails = rand() < 0.42 ? Math.floor(rand() * 3) + (rand() < 0.12 ? 2 : 0) : 0;
  const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  days.push({ date: iso, runs, fails });
}
export const DAILY = days;

// Weekly fail rate (%), for the trend chart.
export const WEEKLY = (() => {
  const out = [];
  for (let i = 0; i < days.length; i += 7) {
    const w = days.slice(i, i + 7);
    const runs = w.reduce((a, x) => a + x.runs, 0);
    const fails = w.reduce((a, x) => a + x.fails, 0);
    out.push({ label: new Date(`${w[0].date}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }), rate: (100 * fails) / runs, runs, fails });
  }
  return out;
})();

// Capture results in the docs/COMPANION_APP.md result JSON shape.
export const CAPTURES = [
  {
    id: 'c_003', run_id: 'R-1542', at: '2008-10-17T14:12:00', fail_probability: 0.31, risk_band: 'high',
    top_contributors: [
      { feature: 'F59', value: 6.2, shap: 0.18, in_safe_window: false, safe_window: [4.9, 5.4] },
      { feature: 'F103', value: 0.012, shap: 0.09, in_safe_window: false, safe_window: [-0.012, -0.006] },
      { feature: 'F21', value: -4600, shap: -0.02, in_safe_window: true, safe_window: [-4720, -4560] },
    ],
    needs_review: ['F333'], imputed: ['F486'], disclaimer: 'Association-based estimate, not proven cause.',
  },
  {
    id: 'c_002', run_id: 'R-1537', at: '2008-10-17T11:40:00', fail_probability: 0.09, risk_band: 'medium',
    top_contributors: [
      { feature: 'F333', value: 1.31, shap: 0.05, in_safe_window: false, safe_window: [1.02, 1.11] },
      { feature: 'F59', value: 5.1, shap: -0.04, in_safe_window: true, safe_window: [4.9, 5.4] },
      { feature: 'F129', value: 0.31, shap: -0.02, in_safe_window: true, safe_window: [0.29, 0.34] },
    ],
    needs_review: [], imputed: [], disclaimer: 'Association-based estimate, not proven cause.',
  },
  {
    id: 'c_001', run_id: 'R-1529', at: '2008-10-16T16:05:00', fail_probability: 0.03, risk_band: 'low',
    top_contributors: [
      { feature: 'F59', value: 5.0, shap: -0.06, in_safe_window: true, safe_window: [4.9, 5.4] },
      { feature: 'F103', value: -0.009, shap: -0.03, in_safe_window: true, safe_window: [-0.012, -0.006] },
      { feature: 'F486', value: 19.4, shap: -0.01, in_safe_window: true, safe_window: [18.2, 21.6] },
    ],
    needs_review: [], imputed: ['F21'], disclaimer: 'Association-based estimate, not proven cause.',
  },
];
