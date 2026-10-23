import { ArrowRight, ShieldCheck, ShieldQuestion } from 'lucide-react';
import StatCards from '../components/dashboard/StatCards';
import { ChartCard, LineChart } from '../components/charts';
import { Banner, CardTitle } from '../components/ui';
import { navigate } from '../lib/router';
import { DATASET, METRICS, RANKING, SPLIT, WEEKLY } from '../data/sample';

// Index of the week a date falls in, for the split markers on the trend chart.
const weekOf = (date) => Math.floor((new Date(`${date}T00:00:00`) - new Date(`${DATASET.start}T00:00:00`)) / (7 * 864e5));

export const StableChip = ({ stable }) => (
  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${stable ? 'bg-good/12 text-good' : 'bg-ink/8 text-ink/65'}`}>
    {stable ? <ShieldCheck size={12} /> : <ShieldQuestion size={12} />}
    {stable ? 'Stable' : 'Unstable'}
  </span>
);

const TopDrivers = () => (
  <section className="card">
    <CardTitle
      sub="Mean rank over 50 refits. Association, not cause."
      action={
        <button type="button" onClick={() => navigate('ranking')} className="btn-ghost h-8 px-3 text-xs">
          Full ranking <ArrowRight size={13} />
        </button>
      }
    >
      Where to look first
    </CardTitle>
    <ol className="flex flex-col divide-y divide-ink/8">
      {RANKING.slice(0, 5).map((r, i) => (
        <li key={r.feature} className="flex items-center gap-3 py-2.5">
          <span className="tabular w-5 text-sm font-semibold text-ink/45">{i + 1}</span>
          <span className="min-w-0 flex-1">
            <span className="font-mono text-sm font-semibold">{r.feature}</span>
            <span className="ml-2 text-xs text-ink/55">group {r.group}</span>
          </span>
          <span className="tabular text-xs text-ink/60">rank {r.meanRank.toFixed(1)} ± {r.rankStd.toFixed(1)}</span>
          <StableChip stable={r.stable} />
        </li>
      ))}
    </ol>
  </section>
);

const DataHandling = () => (
  <section className="card">
    <CardTitle sub="docs/ML_SPEC.md §1, §2 and §4.">Data handling</CardTitle>
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
      {[
        ['Columns kept', DATASET.featuresKept],
        ['Dropped, constant', DATASET.droppedConstant],
        ['Dropped, >60% missing', DATASET.droppedMissing],
        ['Missingness flags', DATASET.missingFlags],
      ].map(([k, v]) => (
        <div key={k} className="rounded-xl bg-ink/5 p-3">
          <dd className="tabular text-xl font-bold">{v}</dd>
          <dt className="text-xs text-ink/60">{k}</dt>
        </div>
      ))}
    </dl>
    <table className="mt-4 w-full text-left text-sm">
      <caption className="sr-only">Time-based split</caption>
      <thead className="text-xs text-ink/55">
        <tr><th className="pb-1 font-medium">Window</th><th className="pb-1 font-medium">Dates</th><th className="pb-1 text-right font-medium">Runs</th><th className="pb-1 text-right font-medium">Fails</th></tr>
      </thead>
      <tbody className="tabular">
        {[['Train', SPLIT.train], ['Validation', SPLIT.val], ['Test', SPLIT.test]].map(([k, w]) => (
          <tr key={k} className="border-t border-ink/8">
            <td className="py-1.5 font-medium">{k}</td>
            <td className="py-1.5 text-ink/65">{w.from} to {w.to}</td>
            <td className="py-1.5 text-right">{w.runs}</td>
            <td className="py-1.5 text-right">{w.fails}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>
);

const Confusion = () => {
  const { tp, fp, fn, tn } = METRICS.confusion;
  const cell = (n, label, strong) => (
    <div className={`rounded-xl p-3 ${strong ? 'bg-accent-soft' : 'bg-ink/5'}`}>
      <p className="tabular text-xl font-bold">{n}</p>
      <p className="text-xs text-ink/60">{label}</p>
    </div>
  );
  return (
    <section className="card">
      <CardTitle sub={`Test window, threshold ${METRICS.threshold} chosen from the cost of a missed defect versus a false alarm.`}>Confusion matrix</CardTitle>
      <div className="grid grid-cols-2 gap-2">
        {cell(tp, 'Fails caught', true)}
        {cell(fn, 'Fails missed')}
        {cell(fp, 'False alarms')}
        {cell(tn, 'Passes cleared')}
      </div>
    </section>
  );
};

const Overview = () => {
  const stable = RANKING.filter((r) => r.stable).length;
  return (
    <div className="flex flex-col gap-[var(--gap)]">
      <Banner tone="warn">
        Every number here is sample data in the shape of the real artifacts. Replace <code className="font-mono">src/data/sample.js</code> with the API once <code className="font-mono">make train</code> runs.
      </Banner>
      <StatCards metrics={METRICS} stable={stable} total={RANKING.length} />
      <div className="grid gap-[var(--gap)] 2xl:grid-cols-[1.4fr_1fr]">
        <ChartCard
          title="Weekly fail rate"
          sub="Share of runs that failed, by week. Dashed lines mark where validation and test begin."
          table={{ head: ['Week of', 'Runs', 'Fails', 'Fail rate'], rows: WEEKLY.map((w) => [w.label, w.runs, w.fails, `${w.rate.toFixed(1)}%`]) }}
        >
          <LineChart
            labels={WEEKLY.map((w) => w.label)}
            series={[{ name: 'Fail rate', values: WEEKLY.map((w) => w.rate) }]}
            format={(v) => `${v.toFixed(1)}%`}
            markers={[{ at: weekOf(SPLIT.val.from), label: 'Validation' }, { at: weekOf(SPLIT.test.from), label: 'Test' }]}
            label="Weekly fail rate across the sample period"
          />
        </ChartCard>
        <TopDrivers />
      </div>
      <div className="grid gap-[var(--gap)] xl:grid-cols-2">
        <DataHandling />
        <Confusion />
      </div>
    </div>
  );
};

export default Overview;
