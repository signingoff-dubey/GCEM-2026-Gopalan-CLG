import { useMemo, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { CardTitle, Toggle } from '../components/ui';
import { COST_DEFAULTS, COST_LIMITS, monthlySavings } from '../lib/cost';
import { num, pct, rupees } from '../lib/format';
import { REDUCTION, SPLIT } from '../data/sample';

const BASELINE = SPLIT.train.fails / SPLIT.train.runs; // observed train fail rate (ML_SPEC §7)

const SLIDERS = [
  { key: 'volumePerDay', label: 'Parts per day', fmt: (v) => num(v, 0) },
  { key: 'scrapCostPerPart', label: 'Scrap cost per part', fmt: rupees },
  { key: 'daysPerMonth', label: 'Working days per month', fmt: (v) => v },
  { key: 'falseAlarmCost', label: 'Cost of one false alarm', fmt: rupees, gated: true },
  { key: 'falseAlarmRate', label: 'Good parts flagged by the gate', fmt: (v) => pct(v, 0), gated: true },
];

const Slider = ({ s, value, onChange, disabled }) => {
  const lim = COST_LIMITS[s.key];
  return (
    <label className={`block text-sm ${disabled ? 'opacity-45' : ''}`}>
      <span className="flex justify-between">
        <span className="font-medium">{s.label}</span>
        <span className="tabular font-semibold">{s.fmt(value)}</span>
      </span>
      <input type="range" min={lim.min} max={lim.max} step={lim.step} value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} className="mt-1.5" />
    </label>
  );
};

const Result = ({ label, r, strong }) => (
  <div className={`rounded-2xl p-4 ${strong ? 'bg-accent text-on-accent' : 'bg-ink/5'}`}>
    <p className={`text-xs font-medium ${strong ? 'opacity-80' : 'text-ink/60'}`}>{label}</p>
    <p className="tabular mt-1 text-2xl font-bold tracking-tight">{rupees(r.net)}</p>
    <p className={`tabular mt-1 text-xs ${strong ? 'opacity-80' : 'text-ink/60'}`}>{num(r.avoidedPartsPerMonth, 0)} scrap parts avoided</p>
  </div>
);

const Savings = () => {
  const [p, setP] = useState(COST_DEFAULTS);
  const set = (k) => (v) => setP((cur) => ({ ...cur, [k]: v }));
  const out = useMemo(() => monthlySavings(p, BASELINE, REDUCTION), [p]);

  return (
    <div className="grid gap-[var(--gap)] xl:grid-cols-[1fr_1.2fr]">
      <section className="card">
        <CardTitle
          sub="Your line's numbers. Nothing here is sent anywhere."
          action={
            <button type="button" onClick={() => setP(COST_DEFAULTS)} className="btn-ghost h-8 px-3 text-xs">
              <RotateCcw size={13} /> Reset
            </button>
          }
        >
          Assumptions
        </CardTitle>
        <div className="flex flex-col gap-4">
          {SLIDERS.map((s) => <Slider key={s.key} s={s} value={p[s.key]} onChange={set(s.key)} disabled={s.gated && !p.gated} />)}
          <div className="flex items-center justify-between gap-3 rounded-xl border border-ink/10 px-3 py-2.5 text-sm">
            <span>
              <span className="font-medium">The model gates parts</span>
              <span className="block text-xs text-ink/60">Flagged parts are pulled for inspection, so false alarms cost money.</span>
            </span>
            <Toggle checked={p.gated} onChange={set('gated')} label="The model gates parts" />
          </div>
        </div>
      </section>

      <div className="flex flex-col gap-[var(--gap)]">
        <section className="card">
          <CardTitle sub="Per month, after false-alarm cost. Low and high come from the confidence interval of the fail-rate reduction.">
            Model-estimated savings
          </CardTitle>
          <div className="grid gap-3 sm:grid-cols-3">
            <Result label={`Low (${pct(REDUCTION.low, 0)} fewer fails)`} r={out.low} />
            <Result label={`Mid (${pct(REDUCTION.mid, 0)} fewer fails)`} r={out.mid} strong />
            <Result label={`High (${pct(REDUCTION.high, 0)} fewer fails)`} r={out.high} />
          </div>
          {out.low.net < 0 && <p className="mt-3 rounded-xl bg-bad/12 px-3 py-2 text-sm font-medium">At the low end the false alarms cost more than the scrap saved.</p>}
        </section>
        <section className="card">
          <CardTitle sub="docs/ML_SPEC.md §7. The same formula will run in backend/ml/cost.py.">How it is worked out</CardTitle>
          <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-sm text-ink/80">
            <li>Baseline fail rate is the observed train rate: <span className="tabular font-semibold">{pct(BASELINE)}</span>.</li>
            <li>Scrap avoided per day = parts per day × baseline × reduction.</li>
            <li>Gross saving = scrap avoided × scrap cost × working days.</li>
            <li>{p.gated ? <>Minus false alarms: good parts × flag rate × false-alarm cost × working days (<span className="tabular font-semibold">{rupees(out.mid.falseAlarmCost)}</span> at mid).</> : 'No false-alarm cost: the model is not gating parts.'}</li>
          </ol>
          <p className="mt-3 text-xs text-ink/60">A model estimate under the assumptions above, not a promise. The reduction comes from historical association; a pilot on the line would confirm it.</p>
        </section>
      </div>
    </div>
  );
};

export default Savings;
