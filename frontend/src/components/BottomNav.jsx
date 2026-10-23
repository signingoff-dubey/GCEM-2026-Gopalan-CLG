import { flowSteps } from '../navigation';
import Liquid from './ui/Liquid';

// Floating pill with the three answers: where it breaks, what to change, how much it saves.
// Doubles as the phone bottom bar.
const BottomNav = ({ active, onSelect }) => (
  <nav aria-label="Analysis steps" className="fixed bottom-4 left-1/2 z-40 -translate-x-1/2 lg:absolute">
    <ol className="flex items-center gap-0.5 glass-chip rounded-full p-1">
      {flowSteps.map(({ slug, label, icon: Icon }) => {
        const isActive = active === slug;
        return (
          <li key={slug}>
            <button
              type="button"
              onClick={() => onSelect(slug)}
              aria-current={isActive ? 'step' : undefined}
              aria-label={label}
              className={`relative flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium transition-colors ${isActive ? 'text-on-accent' : 'text-white/60 hover:text-white'}`}
            >
              {isActive && <Liquid layoutId="bottom-nav-pill" axis="x" className="inset-0 rounded-full" />}
              <Icon size={16} className="relative shrink-0" />
              <span className={`relative whitespace-nowrap ${isActive ? '' : 'hidden md:inline'}`}>{label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  </nav>
);

export default BottomNav;
