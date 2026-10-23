import { CheckCircle2, Database } from 'lucide-react';
import { CardTitle } from '../components/ui';
import Gate from '../components/ui/Gate';
import { useApi } from '../lib/useApi';
import { num, pct } from '../lib/format';

// Missing values and outliers: what cleaning did, fitted on the training window only, and the check that the
// training data kept its shape. Problem statement: "handle missing and imbalanced data".
const Stat = ({ k, v, sub }) => (
  <div className="rounded-xl bg-ink/5 px-3 py-2.5">
    <p className="text-xs text-ink/55">{k}</p>
    <p className="tabular text-lg font-semibold">{v}</p>
    {sub && <p className="text-[11px] text-ink/55">{sub}</p>}
  </div>
);

const Drift = () => {
  const q = useApi('/api/drift');
  return (
    <Gate q={q} what="The drift report">
      {({ report: r, experiment: e }) => (
        <>
          <section className="card">
            <CardTitle sub={`Recorded ${r.data_period.first_run.slice(0, 10)} to ${r.data_period.last_run.slice(0, 10)}; test window from ${r.data_period.test[0].slice(0, 10)}. Real dates are never extended.`}>Drift between training and later runs</CardTitle>
            <div className="grid grid-cols-3 gap-2">
              <Stat k="Train vs test separable" v={num(r.adversarial.auc, 3)} sub={`AUC, ${r.adversarial.badge}`} />
              <Stat k="Sensors shifted" v={`${num(r.sensors_shifted_psi_gt_0_25, 0)} / ${num(r.sensors_checked, 0)}`} sub="PSI above 0.25" />
              <Stat k="Most shifted" v={r.most_shifted[0]?.feature ?? '-'} sub={`KS ${num(r.most_shifted[0]?.ks ?? 0, 2)}`} />
            </div>
            <p className="mt-3 text-xs text-ink/60">How we manage it: split by time only, a re-check of every safe window on the later test window, rolling-origin evaluation and the Timeline view. Windows that do not hold later are marked not recommended.</p>
          </section>
          <section className="card">
            <CardTitle sub={e.chosen_on}>Can training adapt to drift?</CardTitle>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-ink/55"><tr><th className="py-1">Variant</th><th className="text-right">Validation PR-AUC</th><th className="text-right">Test PR-AUC</th></tr></thead>
              <tbody>
                {Object.entries(e.variants).map(([k, v]) => (
                  <tr key={k} className={`border-t border-ink/8 ${k === e.best_on_validation ? 'font-semibold' : ''}`}>
                    <td className="py-1.5 capitalize">{k === 'interpolation' ? 'Interpolated extra runs' : k === 'recency' ? 'Recent runs weighted more' : 'Current model'}</td>
                    <td className="tabular text-right">{num(v.val_pr_auc, 3)} ± {num(v.val_sd, 3)}</td>
                    <td className="tabular text-right">{num(v.test_pr_auc, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 rounded-xl bg-ink/5 px-3 py-2 text-sm font-medium">{e.decision}</p>
            <p className="mt-2 text-xs text-ink/55">{e.note} Each variant here trains on the training window only, so its scores are lower than the final model's, which also learns from validation.</p>
          </section>
        </>
      )}
    </Gate>
  );
};

const DataQuality = () => {
  const q = useApi('/api/data-quality');
  return (
    <Gate q={q} what="The data quality report">
      {(d) => (
        <div className="grid gap-[var(--gap)] xl:grid-cols-2">
          <section className="card xl:col-span-2">
            <CardTitle sub={`${d.method.imputed_with}; outliers ${d.method.outliers}; ${d.method.fitted_on}.`}>
              <span className="flex items-center gap-2"><Database size={17} /> How missing values and outliers are handled</span>
            </CardTitle>
            <ol className="flex flex-col gap-1.5 text-sm">
              {d.steps.map((s, i) => (
                <li key={s} className="flex gap-2"><span className="tabular font-semibold text-accent-deep">{i + 1}.</span> {s}</li>
              ))}
            </ol>
          </section>

          <section className="card">
            <CardTitle sub="Gaps filled and outliers clipped in each split, using the training window's statistics only.">Per split</CardTitle>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-ink/55">
                <tr><th className="py-1">Split</th><th className="text-right">Runs</th><th className="text-right">Fail rate</th><th className="text-right">Gaps filled</th><th className="text-right">Gaps left</th><th className="text-right">Outliers clipped</th></tr>
              </thead>
              <tbody>
                {Object.entries(d.splits).map(([k, s]) => (
                  <tr key={k} className="border-t border-ink/8">
                    <td className="py-1.5 font-medium capitalize">{k}</td>
                    <td className="tabular text-right">{num(s.rows, 0)}</td>
                    <td className="tabular text-right">{pct(s.fail_rate)}</td>
                    <td className="tabular text-right">{num(s.missing_before, 0)}</td>
                    <td className="tabular text-right">{num(s.missing_after, 0)}</td>
                    <td className="tabular text-right">{num(s.outliers_clipped, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-ink/60">Imbalance: {d.imbalance.handled_by}.</p>
          </section>

          <section className="card">
            <CardTitle sub={d.shape_check.note}>Did cleaning change the training data?</CardTitle>
            <div className="grid grid-cols-3 gap-2">
              <Stat k="Typical mean shift" v={`${num(d.shape_check.median_mean_shift_sd, 3)} sd`} sub="median over sensors" />
              <Stat k="Worst 5% shift" v={`${num(d.shape_check.p95_mean_shift_sd, 3)} sd`} sub="95th percentile" />
              <Stat k="Spread kept" v={pct(d.shape_check.median_std_ratio, 0)} sub="median std after / before" />
            </div>
            <p className="mt-3 flex items-start gap-2 rounded-xl bg-good/12 px-3 py-2 text-sm">
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-good" />
              {d.shape_check.features} sensors kept. A typical sensor&apos;s mean moves by about a hundredth of a standard deviation, so filling and clipping do not reshape the training data; clipping trims only the extreme tails.
            </p>
          </section>

          <Drift />

          <section className="card xl:col-span-2">
            <CardTitle sub="Sensors kept despite gaps: the fill value and the clip range are learned on the training window.">Most-missing sensors</CardTitle>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs text-ink/55">
                  <tr><th className="py-1">Sensor</th><th className="text-right">Missing (train)</th><th className="text-right">Filled with</th><th className="text-right">Clip range</th><th className="text-right">Was-missing flag</th></tr>
                </thead>
                <tbody>
                  {d.most_missing.map((f) => (
                    <tr key={f.feature} className="border-t border-ink/8">
                      <td className="py-1.5 font-mono">{f.feature}</td>
                      <td className="tabular text-right">{pct(f.missing_train)}</td>
                      <td className="tabular text-right">{num(f.fill_value, 4)}</td>
                      <td className="tabular text-right">{num(f.clip_low, 3)} to {num(f.clip_high, 3)}</td>
                      <td className="text-right">{f.flagged ? 'yes' : 'no'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </Gate>
  );
};

export default DataQuality;
