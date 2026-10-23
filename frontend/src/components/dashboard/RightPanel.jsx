import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PanelRightClose, PanelRightOpen, TriangleAlert, CircleCheck, CircleDot, X } from 'lucide-react';
import { Calendar, DateRail, useDayModel } from './CalendarParts';
import { navigate } from '../../lib/router';
import { CAPTURES, DAILY, DATASET, SPLIT } from '../../data/sample';

const Profile = () => {
  const stats = [
    { value: DATASET.runs.toLocaleString('en-IN'), label: 'Runs' },
    { value: DATASET.fails, label: 'Fails' },
    { value: DATASET.features, label: 'Features' },
  ];
  return (
    <div>
      <div className="flex items-center gap-3">
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-accent font-semibold text-on-accent">{DATASET.name.slice(0, 2)}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{DATASET.name}</p>
          <p className="truncate text-xs text-white/55">{DATASET.line}</p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 divide-x divide-white/10 rounded-2xl bg-black/20 py-3 text-center">
        {stats.map((s) => (
          <div key={s.label}>
            <dd className="tabular text-lg font-semibold">{s.value}</dd>
            <dt className="text-xs text-white/55">{s.label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
};

const BAND = {
  high: { icon: TriangleAlert, tone: 'text-bad bg-bad/20', tag: 'High risk' },
  medium: { icon: CircleDot, tone: 'text-warn bg-warn/20', tag: 'Medium risk' },
  low: { icon: CircleCheck, tone: 'text-good bg-good/20', tag: 'Low risk' },
};

const RecentCaptures = () => (
  <section>
    <div className="flex items-center justify-between">
      <h2 className="font-semibold">Recent captures</h2>
      <button type="button" onClick={() => navigate('captures')} className="text-sm text-white/60 hover:text-white">View all</button>
    </div>
    <ul className="mt-3 flex flex-col gap-2">
      {CAPTURES.map((c) => {
        const { icon: Icon, tone, tag } = BAND[c.risk_band];
        const off = c.top_contributors.filter((t) => !t.in_safe_window).length;
        return (
          <li key={c.id}>
            <button type="button" onClick={() => navigate('captures', c.id)} className="flex w-full items-center gap-3 rounded-2xl bg-black/20 p-2.5 text-left transition-colors hover:bg-black/30">
              <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${tone}`}>
                <Icon size={18} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="rounded-md bg-white/10 px-1.5 py-0.5 text-[11px] font-medium text-white/75">{tag}</span>
                <span className="mt-1 block truncate text-sm font-semibold">Run {c.run_id}</span>
                <span className="block truncate text-xs text-white/55">{off ? `${off} driver${off > 1 ? 's' : ''} outside safe window` : 'All top drivers inside safe windows'}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  </section>
);

const KEY = 'right-expanded';
const RAIL = 64;
const WIDE = 320;

const readExpanded = () => {
  try {
    return localStorage.getItem(KEY) !== '0';
  } catch {
    return true;
  }
};

// Content keeps its full width while the panel grows or shrinks around it (the panel clips), so nothing reflows
// mid-animation. Width minus 11px padding and 1px border on each side.
const INNER_WIDE = WIDE - 24;
const INNER_RAIL = RAIL - 24;
const EASE = [0.4, 0, 0.2, 1];

// Opening: the sections follow the growing edge in, one after another. Closing: they fade out at once.
const list = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { delayChildren: 0.08, staggerChildren: 0.07 } },
  exit: { opacity: 0, transition: { duration: 0.12 } },
};
const item = {
  hidden: { opacity: 0, x: 28, filter: 'blur(6px)' },
  show: { opacity: 1, x: 0, filter: 'blur(0px)', transition: { type: 'spring', stiffness: 260, damping: 26 } },
};

// The calendar opens on the last month of data, not today, since the SECOM runs are from 2008.
const LAST = new Date(`${DATASET.end}T00:00:00`);

const Summary = ({ model, picked, onPick }) => (
  <>
    <motion.div variants={item}><Profile /></motion.div>
    <motion.div variants={item}><Calendar model={model} picked={picked} onPick={onPick} start={LAST} /></motion.div>
    <motion.div variants={item}><RecentCaptures /></motion.div>
  </>
);

// Below xl the panel has no room beside the main panel, so it slides in from the right instead.
const Drawer = ({ onClose, children }) => {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] xl:hidden">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <motion.aside
        aria-label="Dataset summary"
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', stiffness: 360, damping: 38 }}
        className="absolute inset-y-0 right-0 w-[min(22rem,90vw)] p-3"
      >
        <div className="glass-panel flex h-full flex-col rounded-3xl p-3">
          <div className="flex items-center justify-between">
            <h2 className="pl-1 text-base font-semibold">Summary</h2>
            <button type="button" onClick={onClose} aria-label="Close the calendar panel" className="grid size-10 place-items-center rounded-xl text-white/70 hover:bg-white/10 hover:text-white">
              <X size={20} />
            </button>
          </div>
          <motion.div variants={list} initial="hidden" animate="show" className="mt-3 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-1 pb-1">
            {children}
          </motion.div>
        </div>
      </motion.aside>
    </div>
  );
};

const RightPanel = ({ drawerOpen = false, onCloseDrawer }) => {
  const [expanded, setExpanded] = useState(readExpanded);
  const [picked, setPicked] = useState(null); // the clicked date, shared by the calendar, the rail and the drawer

  useEffect(() => {
    try {
      localStorage.setItem(KEY, expanded ? '1' : '0');
    } catch {
      // Storage blocked: the panel just opens expanded next time.
    }
  }, [expanded]);

  const model = useDayModel(DAILY, SPLIT);

  return (
    <>
      <motion.aside
        aria-label="Dataset summary"
        initial={false}
        animate={{ width: expanded ? WIDE : RAIL }}
        transition={{ duration: 0.34, ease: EASE }}
        style={{ willChange: 'width' }}
        className="glass-panel hidden shrink-0 flex-col overflow-hidden rounded-[28px] p-[11px] xl:flex"
      >
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? 'Collapse the calendar panel' : 'Expand the calendar panel'}
          aria-expanded={expanded}
          title={expanded ? 'Collapse' : 'Expand'}
          className="grid size-10 shrink-0 place-items-center self-start rounded-xl text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <motion.span key={expanded ? 'close' : 'open'} initial={{ opacity: 0, rotate: expanded ? -90 : 90 }} animate={{ opacity: 1, rotate: 0 }} transition={{ duration: 0.25, ease: EASE }}>
            {expanded ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
          </motion.span>
        </button>
        <div className="relative mt-2 min-h-0 flex-1">
          <AnimatePresence initial={false}>
            {expanded ? (
              <motion.div
                key="summary"
                variants={list}
                initial="hidden"
                animate="show"
                exit="exit"
                style={{ width: INNER_WIDE }}
                className="absolute inset-y-0 left-0 flex flex-col gap-4 overflow-y-auto px-1 pb-1"
              >
                <Summary model={model} picked={picked} onPick={setPicked} />
              </motion.div>
            ) : (
              <motion.div
                key="rail"
                initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)', transition: { delay: 0.18, duration: 0.25, ease: EASE } }}
                exit={{ opacity: 0, transition: { duration: 0.1 } }}
                style={{ width: INNER_RAIL }}
                className="absolute inset-y-0 left-0 flex flex-col"
              >
                <DateRail
                  start={LAST}
                  model={model}
                  picked={picked}
                  onPick={(d) => {
                    setPicked(d);
                    setExpanded(true);
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.aside>
      <AnimatePresence>
        {drawerOpen && (
          <Drawer onClose={onCloseDrawer}>
            <Summary model={model} picked={picked} onPick={setPicked} />
          </Drawer>
        )}
      </AnimatePresence>
    </>
  );
};

export default RightPanel;
