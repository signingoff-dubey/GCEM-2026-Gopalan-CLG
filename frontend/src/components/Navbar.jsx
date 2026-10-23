import { useEffect, useState } from 'react';
import { Menu, PanelRightOpen, FlaskConical } from 'lucide-react';
import { SyncDot, ProviderChip } from './ui';
import { health, readApiSettings } from '../lib/api';
import { DATASET } from '../data/sample';

const greeting = () => {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
};

// Top bar: page title, what the page is for, the data source and whether the API answers.
// Until backend/api exists the ping fails and the dot says Offline; the screens keep running on sample data.
const Navbar = ({ page, onOpenMenu, onOpenSummary }) => {
  const [status, setStatus] = useState(null); // null while checking, false when unreachable
  const isHome = page.slug === 'home';

  useEffect(() => {
    let live = true;
    const ping = () => health().then((h) => live && setStatus(h)).catch(() => live && setStatus(false));
    ping();
    const t = setInterval(ping, readApiSettings().pollMs * 5);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  const sync = status ? 'connected' : status === false ? 'offline' : 'reconnecting';

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-2">
        <button type="button" aria-label="Open menu" onClick={onOpenMenu} className="-ml-2 grid size-10 shrink-0 place-items-center rounded-xl text-white/80 hover:bg-white/10 lg:hidden">
          <Menu size={20} />
        </button>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">{isHome ? `${greeting()}` : page.label}</h1>
          <p className="mt-0.5 max-w-xl text-sm text-white/60">{page.description}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-warn/20 px-2.5 py-1 text-xs font-medium text-white/85 ring-1 ring-warn/40">
              <FlaskConical size={12} /> Sample data
            </span>
            <ProviderChip name={`${DATASET.name}, ${DATASET.runs.toLocaleString('en-IN')} runs`} />
            <SyncDot state={sync} />
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={onOpenSummary}
        aria-label="Open the calendar panel"
        title="Calendar and recent captures"
        className="grid size-10 place-items-center rounded-full bg-black/25 text-white/70 ring-1 ring-white/10 transition-colors hover:text-white xl:hidden"
      >
        <PanelRightOpen size={18} />
      </button>
    </header>
  );
};

export default Navbar;
