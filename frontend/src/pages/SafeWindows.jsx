import { useState } from 'react';
import { CardTitle, Tabs } from '../components/ui';
import { num, pct } from '../lib/format';
import { navigate } from '../lib/router';
import { SAFE_WINDOWS } from '../data/sample';

// Position of a value on the bound strip, 0..100.
const at = (w, v) => ((v - w.bound[0]) / (w.bound[1] - w.bound[0])) * 100;

// The observed range (p5..p95) as a strip, the safe window as an accent band, the current median as a tick,
// and an optional what-if marker. Nothing can be drawn outside the strip: the bound is the whole axis.
const Strip = ({ w, value }) => (
  <div>
    <div className="relative h-9 rounded-xl bg-ink/6" aria-hidden="true">
      <span className="absolute inset-y-1 rounded-lg bg-accent/35 ring-1 ring-accent" style={{ left: `${at(w, w.window[0])}%`, width: `${at(w, w.window[1]) - at(w, w.window[0])}%` }} />
      <span className="absolute inset-y-0 w-0.5 bg-ink" style={{ left: `${at(w, w.median)}%` }} />
      {value !== undefined && <span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-ink shadow" style={{ left: `${at(w, value)}%` }} />}
    </div>
    <div className="tabular mt-1 flex justify-between text-[11px] text-ink/55">
      <span>p5 {num(w.bound[0], 3)}</span>
      <span>p95 {num(w.bound[1], 3)}</span>
    </div>
  </div>
);

// Failure rate with its Wilson CI as a bar on a 0..12% scale.
const RateBar = ({ label, n, rate, strong }) => {
  const s = (v) => `${Math.min(v / 0.12, 1) * 100}%`;
  return (
    <div className="text-xs">
      <div className="flex justify-between">
        <span className="font-medium">{label}</span>
        <span className="tabular text-ink/65">{pct(rate.value)} ({pct(rate.ci[0])} to {pct(rate.ci[1])}), n={n}</span>
      </div>
      <div className="relative mt-1 h-2 rounded-full bg-ink/8">
        <span className={`absolute inset-y-0 rounded-full ${strong ? 'bg-accent/40' : 'bg-ink/20'}`} style={{ left: s(rate.ci[0]), width: `calc(${s(rate.ci[1])} - ${s(rate.ci[0])})` }} />
        <span className={`absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${strong ? 'bg-accent' : 'bg-ink/60'}`} style={{ left: s(rate.value) }} />
      </div>
    </div>
  );
};

const WindowCard = ({ w, active, onPick }) => (
  <section className={`card ${active ? 'ring-2 ring-accent' : ''}`}>
    <CardTitle
      sub={`Move from median ${num(w.median, 3)} to ${num(w.window[0], 3)} to ${num(w.window[1], 3)}.`}
      action={<button type="button" onClick={onPick} className="btn-ghost h-8 px-3 text-xs">Try it</button>}
    >
      <span className="font-mono">{w.feature}</span>
    </CardTitle>
    <Strip w={w} />
    <div className="mt-4 flex flex-col gap-2.5">
      <RateBar label="Inside the window" n={w.nIn} rate={w.rateIn} strong />
      <RateBar label="Outside" n={w.nOut} rate={w.rateOut} />
    </div>
    <p className="mt-3 rounded-xl bg-ink/5 p-2.5 text-xs text-ink/70">
      Test window check (not used to pick the window): {pct(w.testCheck.rateIn)} inside (n={w.testCheck.nIn}) versus {pct(w.testCheck.rateOut)} outside (n={w.testCheck.nOut}).
    </p>
  </section>
);

// What-if: move one driver within its observed range, others fixed. The slider cannot leave p5..p95 (CLAUDE.md rule 6).
const WhatIf = ({ w }) => {
  const [value, setValue] = useState(w.median);
  const inside = value >= w.window[0] && value <= w.window[1];
  const hist = inside ? w.rateIn : w.rateOut;
  // shortcut: two fixed model-estimated points (outside / inside), until the API rescores the row for each slider value.
  const est = inside ? w.modelEst.after : w.modelEst.before;
  const step = (w.bound[1] - w.bound[0]) / 200;
  return (
    <section className="card">
      <CardTitle sub="Others stay at their medians. The slider stops at the range the line has run.">
        What if <span className="font-mono">{w.feature}</span> moved?
      </CardTitle>
      <Strip w={w} value={value} />
      <label className="mt-3 block text-sm">
        <span className="sr-only">Value of {w.feature}</span>
        <input type="range" min={w.bound[0]} max={w.bound[1]} step={step} value={value} onChange={(e) => setValue(Number(e.target.value))} />
      </label>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl bg-ink/5 p-3">
          <p className="text-xs text-ink/60">Value</p>
          <p className="tabular text-lg font-bold">{num(value, 3)}</p>
          <p className={`text-xs font-semibold ${inside ? 'text-good' : 'text-ink/60'}`}>{inside ? 'Inside the safe window' : 'Outside the safe window'}</p>
        </div>
        <div className="rounded-xl bg-ink/5 p-3">
          <p className="text-xs text-ink/60">Historical fail rate here</p>
          <p className="tabular text-lg font-bold">{pct(hist.value)}</p>
          <p className="tabular text-xs text-ink/60">CI {pct(hist.ci[0])} to {pct(hist.ci[1])}</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-ink/65">
        <span className="rounded bg-warn/15 px-1.5 py-0.5 font-semibold text-warn">Model-estimated</span> fail probability {pct(est)}. The model scoring its own suggestion is circular; trust the historical rate first.
      </p>
      <p className="mt-2 text-xs font-medium text-ink/70">Association, not proof. Confirm with a pilot on the line.</p>
    </section>
  );
};

const SafeWindows = ({ id }) => {
  const start = SAFE_WINDOWS.find((w) => w.feature === id) ?? SAFE_WINDOWS[0];
  const [picked, setPicked] = useState(start.feature);
  const w = SAFE_WINDOWS.find((x) => x.feature === picked) ?? start;
  const pick = (f) => {
    setPicked(f);
    navigate('windows', f);
  };
  return (
    <div className="flex flex-col gap-[var(--gap)]">
      <Tabs tabs={SAFE_WINDOWS.map((x) => x.feature)} active={w.feature} onChange={pick} dark />
      <div className="grid gap-[var(--gap)] xl:grid-cols-2">
        <WhatIf key={w.feature} w={w} />
        <WindowCard w={w} active />
      </div>
      <h2 className="mt-2 text-sm font-semibold text-white/75">All stable drivers</h2>
      <div className="grid gap-[var(--gap)] lg:grid-cols-2 2xl:grid-cols-3">
        {SAFE_WINDOWS.filter((x) => x.feature !== w.feature).map((x) => <WindowCard key={x.feature} w={x} onPick={() => pick(x.feature)} />)}
      </div>
    </div>
  );
};

export default SafeWindows;
