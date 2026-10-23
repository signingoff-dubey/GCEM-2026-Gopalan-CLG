import { useEffect, useState } from 'react';
import { api, apiUrl } from './api';

// Live activity (captures, scan inspections, model uploads) pushed by the server over SSE.
// Falls back to polling when the stream cannot connect, and refreshes when the tab becomes visible again.
const POLL_MS = 10000;

export const useActivity = () => {
  const [state, setState] = useState({ data: null, error: null, live: false });

  useEffect(() => {
    let closed = false;
    let source = null;
    let poll = null;

    const apply = (data) => !closed && setState({ data, error: null, live: Boolean(source && source.readyState === 1) });
    const fetchNow = () => api('/api/activity').then(apply).catch((error) => !closed && setState((s) => ({ ...s, error })));

    const startPolling = () => {
      if (poll) return;
      fetchNow();
      poll = setInterval(fetchNow, POLL_MS);
    };
    const stopPolling = () => {
      clearInterval(poll);
      poll = null;
    };

    if (typeof EventSource === 'function') {
      source = new EventSource(apiUrl('/api/activity/stream'));
      source.addEventListener('activity', (e) => {
        stopPolling();
        try {
          apply(JSON.parse(e.data));
        } catch {
          // ignore a malformed frame; the next one replaces it
        }
      });
      source.addEventListener('tick', (e) => {
        try {
          const { now, today } = JSON.parse(e.data);
          !closed && setState((s) => (s.data ? { ...s, live: true, data: { ...s.data, now, today } } : s));
        } catch {
          // heartbeat only
        }
      });
      // EventSource reconnects by itself; poll in the meantime so the calendar never goes stale.
      source.onerror = () => {
        !closed && setState((s) => ({ ...s, live: false }));
        startPolling();
      };
    } else {
      startPolling();
    }

    const onVisible = () => document.visibilityState === 'visible' && fetchNow();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      closed = true;
      source?.close();
      stopPolling();
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return state;
};

// Local "today" that rolls over at midnight without a reload.
export const useToday = () => {
  const [today, setToday] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date();
      setToday((prev) => (prev.toDateString() === now.toDateString() ? prev : now));
    }, 30000);
    return () => clearInterval(id);
  }, []);
  return today;
};
