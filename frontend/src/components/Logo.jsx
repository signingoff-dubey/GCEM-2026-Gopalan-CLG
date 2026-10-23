import { ScanSearch } from 'lucide-react';

// The RootLens mark: a lens over a scan, on an accent tile. Placeholder until there is a real logo file.
const Logo = ({ size = 28, className = '' }) => (
  <span className={`grid shrink-0 place-items-center rounded-lg bg-accent text-on-accent ${className}`} style={{ width: size, height: size }} aria-hidden="true">
    <ScanSearch size={Math.round(size * 0.62)} strokeWidth={2.25} />
  </span>
);

export default Logo;
