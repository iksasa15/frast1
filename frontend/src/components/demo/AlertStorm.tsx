import { motion, AnimatePresence } from 'motion/react';
import { useOps } from '@/store/useOps';
import clsx from 'clsx';
import type { Incident } from '@/lib/types';

interface Props {
  incident?: Incident | null;
  /** When true, fill available height in a column layout. */
  fill?: boolean;
}

/** Alert feed / storm summary — parent places it (no absolute positioning). */
export function AlertStorm({ incident, fill = false }: Props) {
  const alerts = useOps((s) => s.alerts);
  const raw = Math.max(alerts.length, incident?.rawAlertCount ?? 0);
  const hasIncident = Boolean(incident);
  const noise =
    raw > 0 && hasIncident ? Math.min(99.9, (1 - 1 / raw) * 100) : null;

  if (hasIncident) {
    return (
      <div className={clsx('rq-panel rq-panel--quiet overflow-hidden', fill && 'flex min-h-0 flex-1 flex-col')}>
        <div className="rq-slab-title">
          <span>Alert storm → one cause</span>
          {noise != null && (
            <span className="rq-metric text-[var(--brand-text)]">{noise.toFixed(1)}%</span>
          )}
        </div>
        <div className="grid grid-cols-[1fr_20px_1fr] items-stretch">
          <div className="px-3 py-2.5">
            <div className="rq-kicker text-[var(--crit)]">NMS</div>
            <div className="rq-metric mt-1.5 text-2xl text-[var(--crit)] line-through decoration-1 opacity-80">
              {raw}
            </div>
            <div className="mt-0.5 text-[10px] text-[var(--text-3)]">raw alerts</div>
          </div>
          <div className="flex items-center justify-center text-[var(--brand-text)]">→</div>
          <div className="border-s border-[var(--border-subtle)] px-3 py-2.5">
            <div className="rq-kicker text-[var(--brand-text)]">RootIQ</div>
            <div className="rq-metric mt-1.5 text-2xl text-[var(--brand-text)]">1</div>
            <div className="mt-0.5 truncate text-[10px] text-[var(--text-2)]">
              {incident?.rootCause?.label ?? 'incident'}
            </div>
          </div>
        </div>
        <ul
          className={clsx(
            'space-y-0 overflow-y-auto border-t border-[var(--border-subtle)]',
            fill ? 'min-h-0 flex-1' : 'max-h-28',
          )}
        >
          <AnimatePresence initial={false}>
            {alerts.slice(0, 8).map((a) => (
              <motion.li
                key={a.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={clsx(
                  'border-b border-[var(--border-subtle)] px-3 py-1 font-mono text-[10px]',
                  a.severity === 'critical' ? 'text-[var(--crit)]' : 'text-[var(--warn)]',
                )}
              >
                {a.sourceId} · {a.metric}={a.value}
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        'rq-panel rq-panel--quiet flex flex-col overflow-hidden',
        fill ? 'min-h-0 flex-1' : 'h-56',
      )}
    >
      <div className="rq-slab-title">
        <span>Traditional NMS feed</span>
        <span className="rq-metric text-[var(--crit)]">{alerts.length}</span>
      </div>
      <ul className="min-h-0 flex-1 space-y-0 overflow-y-auto">
        <AnimatePresence initial={false}>
          {alerts.slice(0, 30).map((a) => (
            <motion.li
              key={a.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className={clsx(
                'border-b border-[var(--border-subtle)] px-3 py-1.5 font-mono text-[11px]',
                a.severity === 'critical' ? 'text-[var(--crit)]' : 'text-[var(--warn)]',
              )}
            >
              <div className="truncate">{a.sourceId}</div>
              <div className="text-[var(--text-3)]">
                {a.metric} = {a.value}
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
        {alerts.length === 0 && (
          <li className="px-3 py-6 text-center text-xs text-[var(--text-3)]">
            Waiting for threshold crossings…
          </li>
        )}
      </ul>
    </div>
  );
}
