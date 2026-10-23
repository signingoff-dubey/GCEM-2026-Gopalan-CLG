// The only place the frontend talks to the backend (the FastAPI backend, see its /docs page).
// The base URL comes from Settings > Data, then VITE_API_URL, then the local FastAPI default.
// A 503 means the backend has not generated that artifact yet; ApiError carries the status so screens can say so.
const KEY = 'rootlens-api';

export const API_DEFAULTS = { url: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000', pollMs: 2000 };

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

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export const api = async (path, init = {}) => {
  const res = await fetch(`${readApiSettings().url}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers }, signal: init.signal ?? AbortSignal.timeout(15000) });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // No JSON body: the status line is all there is.
    }
    throw new ApiError(res.status, detail || `${res.status} ${res.statusText} on ${path}`);
  }
  return res.json();
};

export const post = (path, body, init = {}) => api(path, { ...init, method: 'POST', body: JSON.stringify(body) });

export const health = () => api('/api/health');
