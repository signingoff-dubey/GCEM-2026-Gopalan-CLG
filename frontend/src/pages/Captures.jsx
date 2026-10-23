import { useState } from 'react';
import { Camera, ImageUp, CircleCheck, CircleAlert } from 'lucide-react';
import { CardTitle } from '../components/ui';
import { num, pct } from '../lib/format';
import { navigate } from '../lib/router';
import { readApiSettings } from '../lib/api';
import { CAPTURES } from '../data/sample';

const BAND = {
  high: { label: 'High risk', cls: 'bg-bad text-white' },
  medium: { label: 'Medium risk', cls: 'bg-warn text-ink' },
  low: { label: 'Low risk', cls: 'bg-good text-white' },
};

const when = (iso) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

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

const Result = ({ c }) => {
  const band = BAND[c.risk_band];
  const maxShap = Math.max(...c.top_contributors.map((t) => Math.abs(t.shap)), 0.01);
  return (
    <section className="card" aria-live="polite">
      <CardTitle sub={`Capture ${c.id}, ${when(c.at)}`} action={<span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${band.cls}`}>{band.label}</span>}>
        Run {c.run_id}
      </CardTitle>
      <div className="flex flex-wrap items-center gap-5">
        <RiskGauge p={c.fail_probability} />
        <p className="max-w-xs text-sm text-ink/70">Model-estimated chance this run fails, from the values read off the sheet.</p>
      </div>
      <h3 className="mt-4 text-sm font-semibold">Top contributors</h3>
      <ul className="mt-2 flex flex-col gap-2">
        {c.top_contributors.map((t) => (
          <li key={t.feature} className="grid grid-cols-[4rem_1fr_auto] items-center gap-3 rounded-xl bg-ink/5 px-3 py-2 text-sm">
            <span className="font-mono font-semibold">{t.feature}</span>
            <span>
              <span className="tabular block text-xs text-ink/65">value {num(t.value, 3)}, safe window {num(t.safe_window[0], 3)} to {num(t.safe_window[1], 3)}</span>
              <span className="mt-1 block h-1.5 rounded-full bg-ink/8">
                <span className={`block h-full rounded-full ${t.shap > 0 ? 'bg-bad' : 'bg-good'}`} style={{ width: `${(Math.abs(t.shap) / maxShap) * 100}%` }} />
              </span>
            </span>
            <span className={`inline-flex items-center gap-1 text-xs font-semibold ${t.in_safe_window ? 'text-good' : 'text-bad'}`}>
              {t.in_safe_window ? <CircleCheck size={14} /> : <CircleAlert size={14} />}
              {t.in_safe_window ? 'Inside' : 'Outside'}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink/60">Bar length is SHAP size. Red pushes toward failure, green away from it.</p>
      {(c.needs_review.length > 0 || c.imputed.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {c.needs_review.map((f) => <span key={f} className="rounded-full bg-warn/15 px-2 py-0.5 font-semibold text-warn">{f}: check the reading</span>)}
          {c.imputed.map((f) => <span key={f} className="rounded-full bg-ink/8 px-2 py-0.5 font-semibold text-ink/65">{f}: unreadable, train median used</span>)}
        </div>
      )}
      <p className="mt-3 text-xs font-medium text-ink/70">{c.disclaimer}</p>
    </section>
  );
};

// Upload from the laptop, for when the phone app is not there (BUILD_PLAN cut rule). Needs POST /api/captures.
const Upload = () => {
  const [note, setNote] = useState('');
  const pick = (e) => {
    const f = e.target.files?.[0];
    if (f) setNote(`${f.name} is ready, but the capture API at ${readApiSettings().url} is not built yet. Phase 5 adds it.`);
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

const Captures = ({ id }) => {
  const current = CAPTURES.find((c) => c.id === id) ?? CAPTURES[0];
  return (
    <div className="grid gap-[var(--gap)] xl:grid-cols-[1fr_1.4fr]">
      <div className="flex flex-col gap-[var(--gap)]">
        <Upload />
        <section className="card">
          <CardTitle sub="Newest first. The live panel will poll /api/captures/latest.">History</CardTitle>
          <ul className="flex flex-col gap-1">
            {CAPTURES.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => navigate('captures', c.id)}
                  aria-current={c.id === current.id ? 'true' : undefined}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${c.id === current.id ? 'bg-accent-soft' : 'hover:bg-ink/5'}`}
                >
                  <Camera size={16} className="shrink-0 text-ink/55" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">Run {c.run_id}</span>
                    <span className="block text-xs text-ink/55">{when(c.at)}</span>
                  </span>
                  <span className="tabular text-sm font-semibold">{pct(c.fail_probability, 0)}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${BAND[c.risk_band].cls}`}>{BAND[c.risk_band].label}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <Result c={current} />
    </div>
  );
};

export default Captures;
