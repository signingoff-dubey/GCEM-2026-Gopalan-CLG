import { House, ListOrdered, Crosshair, PiggyBank, Camera, Settings, ChartNoAxesColumn, Wrench, Radio } from 'lucide-react';

// Screens of the RootLens dashboard. `slug` is the URL hash (#/ranking).
// Every screen runs on src/data/sample.js until the API exists; see frontend/README.md.
export const pages = {
  home: { slug: 'home', label: 'Overview', icon: House, description: 'How well failures can be predicted on a later time window, and where to look first.' },
  ranking: { slug: 'ranking', label: 'Ranking', icon: ListOrdered, description: 'Statistically suspected drivers of failure, ranked, with stability across 50 bootstrap resamples.' },
  windows: { slug: 'windows', label: 'Safe windows', icon: Crosshair, description: 'Where each stable driver had the lowest failure rate, inside the range the line has run. Association, not proof.' },
  savings: { slug: 'savings', label: 'Savings', icon: PiggyBank, description: 'Model-estimated monthly savings as a range, under the assumptions you set.' },
  captures: { slug: 'captures', label: 'Captures', icon: Camera, description: 'Process sheets photographed on the phone app, read, scored and checked against the safe windows.' },
  settings: { slug: 'settings', label: 'Settings', icon: Settings, description: 'Theme, accent, surfaces, density, the API address and analysis defaults.' },
};

// The rail shows Overview, then groups the user can fold away. A group holding the page you are on always opens.
export const homeItem = pages.home;
export const sidebarGroups = [
  { id: 'analysis', title: 'Analysis', icon: ChartNoAxesColumn, defaultOpen: true, items: [pages.ranking, pages.windows] },
  { id: 'impact', title: 'Impact', icon: Wrench, defaultOpen: true, items: [pages.savings] },
  { id: 'live', title: 'Live', icon: Radio, defaultOpen: true, items: [pages.captures] },
];

export const groupOf = (slug) => sidebarGroups.find((g) => g.items.some((i) => i.slug === slug))?.id;

export const settingsItem = pages.settings;

// The floating pill: the three answers RootLens gives, in order (where, what to change, how much).
export const flowSteps = [pages.ranking, pages.windows, pages.savings];

export const findPage = (slug) => pages[slug];
