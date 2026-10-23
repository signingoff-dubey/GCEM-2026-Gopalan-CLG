import { useEffect, useState } from 'react';
import { Box, Crosshair, Loader2, RefreshCw, TriangleAlert } from 'lucide-react';
import { CardTitle, Toggle } from '../ui';
import { api, post } from '../../lib/api';

// Blender link through the Blender MCP add-on: RootLens reads the open scene, lists the objects
// that carry a defect and can frame one of them in the engineer's Blender viewport.

const put = (path, body) => api(path, { method: 'PUT', body: JSON.stringify(body) });
const fmt = (v) => v.map((x) => x.toFixed(2)).join(', ');

const State = ({ s }) => {
  const map = {
    connected: ['bg-good/15 text-good', 'bg-good animate-pulse', 'Connected'],
    offline: ['bg-bad/12 text-bad', 'bg-bad', 'Not reachable'],
    off: ['bg-ink/8 text-ink/55', 'bg-ink/35', 'Off'],
  };
  const [cls, dot, label] = map[s] ?? map.off;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${cls}`}>
      <span className={`size-1.5 rounded-full ${dot}`} /> {label}
    </span>
  );
};

const IntegrationsTab = () => {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState({});

  const load = () => api('/api/integrations/blender', { signal: AbortSignal.timeout(20000) })
    .then(setSt)
    .catch((e) => setSt((p) => ({ ...(p ?? {}), state: 'offline', connected: false, error: e.message })));
  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  const toggle = async (enabled) => {
    setBusy(true);
    try {
      setSt(await put('/api/integrations/blender', { enabled }));
    } finally {
      setBusy(false);
    }
  };
  const show = async (name) => {
    setFocus((f) => ({ ...f, [name]: 'busy' }));
    try {
      const r = await post('/api/integrations/blender/focus', { name });
      setFocus((f) => ({ ...f, [name]: r.ok ? 'done' : 'missing' }));
    } catch {
      setFocus((f) => ({ ...f, [name]: 'error' }));
    }
  };

  return (
    <div className="grid gap-[var(--gap)] xl:grid-cols-2">
      <section className="card xl:col-span-2">
        <CardTitle
          sub="Link the plant's 3D model in Blender. RootLens finds the defects in the open scene and points to where each one lies."
          action={<Toggle checked={!!st?.enabled} onChange={toggle} label="Blender MCP link" />}
        >
          <span className="flex items-center gap-2"><Box size={17} /> Blender MCP</span>
        </CardTitle>

        {!st ? (
          <p className="flex items-center gap-2 text-sm text-ink/65"><Loader2 size={15} className="animate-spin" /> Checking the link...</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <State s={st.state} />
              <span className="font-mono text-xs text-ink/55">{st.host}:{st.port}</span>
              {st.connected && <span className="text-ink/70">{st.file} · {st.objects} objects · {st.defects?.length ?? 0} defects</span>}
              <button type="button" onClick={load} disabled={busy} className="btn-ghost ml-auto h-9 px-3 text-sm"><RefreshCw size={14} /> Refresh</button>
            </div>
            {st.state === 'offline' && (
              <p className="mt-3 rounded-xl bg-ink/5 px-3 py-2 text-sm text-ink/70">
                Open Blender with the BlenderMCP add-on, press N in the 3D view, open the BlenderMCP tab and click Connect to MCP server.
              </p>
            )}
          </>
        )}
      </section>

      {st?.connected && (
        <section className="card xl:col-span-2">
          <CardTitle sub="Objects in the open scene tagged with a defect, with their position in the model (Blender units).">Where the defects lie</CardTitle>
          {st.defects.length === 0 ? (
            <p className="text-sm text-ink/55">No defect objects in this scene.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs text-ink/55">
                  <tr><th className="py-1.5">Object</th><th>Defect</th><th>Position (x, y, z)</th><th>Size</th><th /></tr>
                </thead>
                <tbody>
                  {st.defects.map((d) => (
                    <tr key={d.name} className="border-t border-ink/8">
                      <td className="py-2 font-medium"><TriangleAlert size={13} className="mr-1.5 inline text-bad" />{d.part || d.name}</td>
                      <td className="capitalize text-ink/70">{d.type}</td>
                      <td className="tabular font-mono text-xs">{fmt(d.center)}</td>
                      <td className="tabular font-mono text-xs">{fmt(d.size)}</td>
                      <td className="text-right">
                        <button type="button" onClick={() => show(d.name)} disabled={focus[d.name] === 'busy'} className="btn-ghost h-8 px-3 text-xs">
                          {focus[d.name] === 'busy' ? <Loader2 size={13} className="animate-spin" /> : <Crosshair size={13} />}
                          {focus[d.name] === 'done' ? 'Shown in Blender' : focus[d.name] === 'error' ? 'Try again' : 'Show in Blender'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
};

export default IntegrationsTab;
