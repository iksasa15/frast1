import { useMemo } from 'react';
import { useOps } from '@/store/useOps';
import type { Incident } from '@/lib/types';
import clsx from 'clsx';

type Mark = {
  key: string;
  label: string;
  symbol: string;
  at?: string;
  color: string;
};

function marksFor(inc: Incident | null, demoInjected?: string | null): Mark[] {
  const t = inc?.timings ?? {};
  return [
    { key: 'inj', label: 'Injected', symbol: '▲', at: demoInjected ?? t.injectedAt, color: 'var(--warn)' },
    { key: 'ano', label: 'First anomaly', symbol: '●', at: t.firstAnomalyAt ?? t.detectedAt, color: 'var(--text-2)' },
    { key: 'open', label: 'Incident opened', symbol: '●', at: inc?.openedAt, color: 'var(--warn)' },
    { key: 'rca', label: 'Root cause', symbol: '◆', at: t.analyzedAt, color: 'var(--crit)' },
    {
      key: 'rej',
      label: 'Rejected',
      symbol: '✕',
      // reject replaces pending action — use rejectedAt (not current action status)
      at: t.rejectedAt,
      color: 'var(--crit)',
    },
    {
      key: 'apr',
      label: 'Approved',
      symbol: '✓',
      at: inc?.action?.approvalStatus === 'approved' || inc?.action?.approvalStatus === 'executed'
        ? t.decidedAt
        : undefined,
      color: 'var(--brand)',
    },
    { key: 'exe', label: 'Executed', symbol: '⚙', at: t.executedAt, color: 'var(--text-2)' },
    { key: 'rec', label: 'Recovered', symbol: '★', at: t.recoveredAt ?? inc?.resolvedAt, color: 'var(--ok)' },
  ];
}

function rel(origin: number, iso?: string) {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - origin;
  if (!Number.isFinite(ms)) return null;
  const s = Math.max(0, Math.round(ms / 1000));
  return `+${s}s`;
}

export function Timeline() {
  const incidents = useOps((s) => s.incidents);
  const alerts = useOps((s) => s.alerts);
  const demo = useOps((s) => s.demo);
  const select = useOps((s) => s.select);

  const active = useMemo(() => {
    const list = Object.values(incidents);
    const open = list.filter((i) => i.status !== 'resolved');
    const pick = (open.length ? open : list).sort((a, b) => b.openedAt.localeCompare(a.openedAt))[0];
    return pick ?? null;
  }, [incidents]);

  const marks = useMemo(
    () => marksFor(active, demo?.injectedAt).filter((m) => m.at),
    [active, demo?.injectedAt],
  );

  const origin = useMemo(() => {
    const first = marks[0]?.at ?? active?.openedAt ?? demo?.injectedAt;
    return first ? new Date(first).getTime() : Date.now();
  }, [marks, active, demo?.injectedAt]);

  const windowMs = 5 * 60 * 1000;
  const now = Date.now();
  const start = now - windowMs;

  const alertDots = useMemo(() => {
    return alerts
      .filter((a) => new Date(a.ts).getTime() >= start)
      .slice(0, 80)
      .map((a) => ({
        id: a.id,
        sourceId: a.sourceId,
        left: ((new Date(a.ts).getTime() - start) / windowMs) * 100,
        crit: a.severity === 'critical',
      }));
  }, [alerts, start]);

  return (
    <div data-testid="timeline" className="flex h-full flex-col gap-2 py-1">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
        <span>Timeline · last 5 minutes</span>
        <span className="font-mono normal-case text-slate-400">
          {active ? active.id : 'no incident'}
        </span>
      </div>

      <div className="relative mx-1 h-10 rounded-lg border border-noc-line/80 bg-noc-bg/40">
        <div className="absolute inset-x-3 top-1/2 h-px -translate-y-1/2 bg-noc-line" />
        {alertDots.map((d) => (
          <button
            key={d.id}
            type="button"
            title={d.sourceId}
            className={clsx(
              'absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full',
              d.crit ? 'bg-crit' : 'bg-warn',
            )}
            style={{ left: `${Math.min(98, Math.max(2, d.left))}%` }}
            onMouseEnter={() =>
              select({
                kind: d.sourceId.startsWith('link-') ? 'link' : 'node',
                id: d.sourceId,
              })
            }
          />
        ))}
      </div>

      <div className="flex flex-wrap gap-2 px-1">
        {marks.length === 0 && (
          <span className="text-[11px] text-slate-500">Waiting for inject / incident milestones…</span>
        )}
        {marks.map((m) => (
          <div
            key={m.key}
            className="flex items-center gap-1.5 rounded border border-noc-line bg-noc-panel/80 px-2 py-1"
          >
            <span style={{ color: m.color }} className="text-sm leading-none">
              {m.symbol}
            </span>
            <span className="text-[11px] text-slate-300">{m.label}</span>
            <span className="font-mono text-[11px] tabular-nums text-slate-500">
              {rel(origin, m.at)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
