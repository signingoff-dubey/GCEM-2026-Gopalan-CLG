import { useState } from 'react';
import { Camera, ImageUp, CircleCheck, CircleAlert } from 'lucide-react';
import { CardTitle, ChipToggle } from '../components/ui';
import Gate, { StatusCard } from '../components/ui/Gate';
import { num, pct } from '../lib/format';
import { navigate } from '../lib/router';
import { readApiSettings } from '../lib/api';
import { useApi } from '../lib/useApi';

const BAND = {
  high: { label: 'High risk', cls: 'bg-bad text-white' },
  elevated: { label: 'Elevated risk', cls: 'bg-warn text-ink' },
  low: { label: 'Low risk', cls: 'bg-good text-white' },
};

// "2008-10-06 03:50:00" is a plain local timestamp, so it is shown as written rather than shifted by the browser's zone.
const when = (ts) => ts.slice(0, 16);

// Half-circle gauge for fail probability, 0..50% scale (SECOM fails are rare).
const RiskGauge = ({ p }) => {
  const len = Math.PI * 40;
  const ratio = Math.min(p / 0.5, 1);
  return (
    <svg viewBox="0 0 100 58" className="w-40" role="img" aria-label={`Fail probability ${pct(p, 0)}`}>
      <path d="M10 52 A40 40 0 0 1 90 52" fill="none" stroke="rgb(31 26 20 / 0.1)" strokeWidth="9" strokeLinecap="round" />
      <path d="M10 52 A40 40 0 0 1 90 52" fill="none" stroke="var(--color-accent)" strokeWidth="9" strokeLinecap="round" strokeDasharray={`${len * ratio} ${len}`} />
      <text x="50" y="48" textAnchor="middle" fontSize="18" fontWeight="700" fill="#1f1a14">{pct(p, 0)}</text>
    </svg>
  );
};

const Counterfactual = ({ cf }) => {
  const est = cf.model_estimate;
  const diffs = cf.biggest_differences.slice(0, 4);
  return (
    <div className="mt-4 rounded-2xl bg-ink/5 p-3">
      <h3 className="text-sm font-semibold">Compared with the {cf.neighbours.length} nearest passing runs</h3>
      <p className="mt-0.5 text-xs text-ink/60">{cf.label}</p>
      {est && (
        <p className="mt-2 text-sm">
          <span className="mr-1.5 rounded bg-warn/15 px-1.5 py-0.5 text-xs font-semibold text-warn">Model-estimated</span>{" "}
          fail probability {pct(est.fail_prob_now, 0)} now, {pct(est.fail_prob_with_nearest_pass_profile, 0)} with the nearest passing profile. The model scoring its own suggestion is circular.
        </p>
      )}
      <ul className="mt-2 flex flex-col gap-1 text-xs text-ink/75">
        {diffs.map((d) => (
          <li key={d.feature} className="tabular flex flex-wrap justify-between gap-x-3">
            <span className="font-mono font-semibold">{d.feature}</span>
            <span>now {num(d.current, 3)}, neighbours {num(d.neighbour_median, 3)} ({num(d.neighbour_range[0], 3)} to {num(d.neighbour_range[1], 3)})</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

const Result = ({ c }) => {
  const band = BAND[c.risk_band] ?? BAND.low;
  const maxShap = Math.max(...c.top_contributors.map((t) => Math.abs(t.shap)), 0.01);
  return (
    <section className="card" aria-live="polite">
      <CardTitle sub={`${when(c.timestamp)}, recorded as ${c.fail ? 'failed' : 'passed'}. Alert threshold ${pct(c.threshold, 0)}.`} action={<span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${band.cls}`}>{band.label}</span>}>
        Run {c.index}
      </CardTitle>
      <div className="flex flex-wrap items-center gap-5">
        <RiskGauge p={c.fail_probability} />
        <p className="max-w-xs text-sm text-ink/70">Model-estimated chance this run fails, from its recorded process values.</p>
      </div>
      <h3 className="mt-4 text-sm font-semibold">Top contributors</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {c.top_contributors.map((t) => (
          <li key={t.feature} className="grid grid-cols-[4rem_1fr_auto] items-center gap-3 rounded-xl bg-ink/5 px-3 py-2 text-sm">
            <span className="font-mono font-semibold">{t.feature}</span>
            <span>
              <span className="tabular block text-xs text-ink/65">
                {t.value === null ? 'value not recorded' : `value ${num(t.value, 3)}`}
                {t.safe_window && `, safe window ${num(t.safe_window[0], 3)} to ${num(t.safe_window[1], 3)}${t.window_status === 'recommended' ? '' : ' (not recommended)'}`}
              </span>
              <span className="mt-1 block h-1.5 rounded-full bg-ink/8">
                <span className={`block h-full rounded-full ${t.shap > 0 ? 'bg-bad' : 'bg-good'}`} style={{ width: `${(Math.abs(t.shap) / maxShap) * 100}%` }} />
              </span>
            </span>
            {typeof t.in_safe_window === 'boolean' && t.window_status === 'recommended' ? (
              <span className={`inline-flex items-center gap-1 text-xs font-semibold ${t.in_safe_window ? 'text-good' : 'text-bad'}`}>
                {t.in_safe_window ? <CircleCheck size={14} /> : <CircleAlert size={14} />}
                {t.in_safe_window ? 'Inside' : 'Outside'}
              </span>
            ) : (
              <span className="text-xs text-ink/45">{t.safe_window ? 'No advice' : ''}</span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink/60">Bar length is SHAP size. Red pushes toward failure, green away from it.</p>
      {c.counterfactual && <Counterfactual cf={c.counterfactual} />}
      <p className="mt-3 text-xs font-medium text-ink/70">{c.disclaimer}</p>
    </section>
  );
};

// Upload from the laptop, for when the phone app is not there (BUILD_PLAN cut rule). The backend has no photo endpoint yet.
const Upload = () => {
  const [note, setNote] = useState('');
  const pick = (e) => {
    const f = e.target.files?.[0];
    if (f) setNote(`${f.name} is ready, but the API at ${readApiSettings().url} has no photo-reading endpoint yet, so nothing was sent.`);
    e.target.value = '';
  };
  return (
    <section className="card">
      <CardTitle sub="Photograph a run sheet on the phone app, or pick a photo here. The vision model reads numbers only.">New capture</CardTitle>
      <label className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-ink/15 px-4 py-8 text-center text-sm transition-colors hover:border-accent hover:bg-accent-soft/40">
        <ImageUp size={24} className="text-ink/55" />
        <span className="font-semibold">Choose a photo of the run sheet</span>
        <span className="text-xs text-ink/55">JPG or PNG</span>
        <input type="file" accept="image/*" capture="environment" onChange={pick} className="sr-only" />
      </label>
      {note && <p role="status" className="mt-3 rounded-xl bg-warn/15 px-3 py-2 text-sm">{note}</p>}
    </section>
  );
};

const Detail = ({ id }) => {
  const q = useApi(`/api/runs/${encodeURIComponent(id)}`);
  return <Gate q={q} what="This run">{(c) => <Result c={c} />}</Gate>;
};

const Body = ({ id, runs, onlyFails, setOnlyFails }) => {
  const list = runs.runs;
  // A run opened from a link may not be in the filtered list; it is still fetched by id.
  const selected = id ?? (list.length ? String(list[list.length - 1].index) : undefined);
  return (
    <div className="grid gap-[var(--gap)] xl:grid-cols-[1fr_1.4fr]">
      <div className="flex flex-col gap-[var(--gap)]">
        <Upload />
        <section className="card">
          <CardTitle
            sub="Runs in the test window, newest first. The probability beside each run is the model's own estimate."
            action={<ChipToggle multiple={false} value={onlyFails ? 'fails' : 'all'} onChange={(v) => setOnlyFails(v === 'fails')} options={[{ id: 'fails', label: 'Failed runs' }, { id: 'all', label: 'All runs' }]} />}
          >
            History
          </CardTitle>
          <ul className="flex max-h-[28rem] flex-col gap-1 overflow-y-auto">
            {[...list].reverse().map((c) => (
              <li key={c.index}>
                <button
                  type="button"
                  onClick={() => navigate('captures', String(c.index))}
                  aria-current={String(c.index) === selected ? 'true' : undefined}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${String(c.index) === selected ? 'bg-accent-soft' : 'hover:bg-ink/5'}`}
                >
                  <Camera size={16} className="shrink-0 text-ink/55" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">Run {c.index}</span>
                    <span className="block text-xs text-ink/55">{when(c.timestamp)}</span>
                  </span>
                  <span className="tabular text-sm font-semibold">{pct(c.fail_prob, 0)}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${c.fail ? 'bg-bad text-white' : 'bg-ink/8 text-ink/65'}`}>{c.fail ? 'Failed' : 'Passed'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {selected ? <Detail key={selected} id={selected} /> : <section className="card text-sm text-ink/65">No runs to show.</section>}
    </div>
  );
};

const Captures = ({ id }) => {
  const [onlyFails, setOnlyFails] = useState(true);
  const q = useApi(`/api/runs?split=test&fails_only=${onlyFails}&limit=300`);
  if (!q.data) return <StatusCard q={q} what="The run history" />;
  return <Body id={id} runs={q.data} onlyFails={onlyFails} setOnlyFails={setOnlyFails} />;
};

export default Captures;
