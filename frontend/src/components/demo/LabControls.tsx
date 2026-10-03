import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export function LabControls() {
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { void api.demoStatus().then((x) => setEnabled(x.enabled)).catch(() => setEnabled(false)); }, []);
  if (!enabled) return null;
  const run = async (restore: boolean) => {
    setBusy(true); setMessage('');
    try { await (restore ? api.restoreUplinkDown : api.triggerUplinkDown)(); setMessage(restore ? 'Restore sent — awaiting healthy telemetry.' : 'Fault injected — awaiting RootIQ detection.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Lab control failed'); }
    finally { setBusy(false); }
  };
  return <div className="absolute left-4 top-4 z-20 flex gap-2 rounded-lg border border-warn/40 bg-noc-panel/95 p-2 text-xs">
    <button disabled={busy} onClick={() => void run(false)} className="rounded bg-crit px-3 py-2 font-semibold text-white disabled:opacity-50">Trigger lab uplink fault</button>
    <button disabled={busy} onClick={() => void run(true)} className="rounded bg-ok px-3 py-2 font-semibold text-black disabled:opacity-50">Restore uplink</button>
    {message && <span className="max-w-52 self-center text-slate-300">{message}</span>}
  </div>;
}
