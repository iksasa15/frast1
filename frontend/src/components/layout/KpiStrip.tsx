import { useMemo } from 'react';
import { useOps } from '@/store/useOps';

function fmtSec(sec: number | null) {
  if (sec == null || !Number.isFinite(sec)) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

export function KpiStrip() {
  const topology = useOps((s) => s.topology);
  const incidents = useOps((s) => s.incidents);

  const { mttd, mttr } = useMemo(() => {
    const resolved = Object.values(incidents)
      .filter((i) => i.status === 'resolved' && i.timings.injectedAt)
      .sort((a, b) => (b.resolvedAt ?? '').localeCompare(a.resolvedAt ?? ''));
    const last = resolved[0];
    if (!last?.timings.injectedAt) return { mttd: null as number | null, mttr: null as number | null };
    const inj = new Date(last.timings.injectedAt).getTime();
    const det = last.timings.detectedAt ? new Date(last.timings.detectedAt).getTime() : null;
    const rec = last.timings.recoveredAt
      ? new Date(last.timings.recoveredAt).getTime()
      : last.resolvedAt
        ? new Date(last.resolvedAt).getTime()
        : null;
    return {
      mttd: det != null ? (det - inj) / 1000 : null,
      mttr: rec != null ? (rec - inj) / 1000 : null,
    };
  }, [incidents]);

  if (!topology) return null;

  const all = [...topology.nodes, ...topology.links, ...topology.services];
  const healthy = all.filter((x) => x.status === 'healthy').length;
  const active = Object.values(incidents).filter((i) => i.status !== 'resolved').length;

  const cards = [
    { label: 'Infra Health', value: `${Math.round((100 * healthy) / Math.max(all.length, 1))}%` },
    { label: 'Active Incidents', value: String(active) },
    {
      label: 'Devices Online',
      value: String(topology.nodes.filter((n) => n.status !== 'unknown').length),
    },
    {
      label: 'Services Affected',
      value: String(topology.services.filter((s) => s.status !== 'healthy').length),
    },
    { label: 'MTTD', value: fmtSec(mttd) },
    { label: 'MTTR', value: fmtSec(mttr) },
  ];
  return (
    <div className="grid grid-cols-6 gap-2 border-b border-noc-line bg-noc-panel/80 px-3 py-2">
      {cards.map((c) => (
        <div key={c.label} className="rounded-lg border border-noc-line bg-noc-bg/40 px-2 py-1.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{c.label}</div>
          <div className="font-mono text-lg tabular-nums transition-all duration-700">{c.value}</div>
        </div>
      ))}
    </div>
  );
}
