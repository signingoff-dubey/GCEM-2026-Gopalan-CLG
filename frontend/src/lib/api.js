// The only place the frontend talks to the backend (docs/COMPANION_APP.md "API").
// The base URL comes from Settings > Data, then VITE_API_URL, then the local FastAPI default.
// Backend not built yet: health() fails and the UI shows Offline. Swap sample imports for these calls page by page.
const KEY = 'rootlens-api';

export const API_DEFAULTS = { url: import.meta.env?.VITE_API_URL || 'http://127.0.0.1:8000', pollMs: 2000 };

export const readApiSettings = () => {
  try {
    return { ...API_DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return { ...API_DEFAULTS };
  }
};

export const saveApiSettings = (patch) => {
  const next = { ...readApiSettings(), ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage blocked: the setting holds until the page reloads.
  }
  return next;
};

export const api = async (path, init = {}) => {
  const res = await fetch(`${readApiSettings().url}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers }, signal: init.signal ?? AbortSignal.timeout(4000) });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json();
};

export const health = () => api('/api/health');
export const latestCapture = () => api('/api/captures/latest');
export const getCapture = (id) => api(`/api/captures/${encodeURIComponent(id)}`);
