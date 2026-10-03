import { useEffect, useState } from 'react';
import clsx from 'clsx';

interface Props {
  injectedAt?: string | null;
  analyzedAt?: string | null;
}

/** Compact MTTD chip — parent places it in the top dock. */
export function MttdStopwatch({ injectedAt, analyzedAt }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!injectedAt || analyzedAt) return;
    let raf = 0;
    const tick = () => {
      setNow(Date.now());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [injectedAt, analyzedAt]);

  if (!injectedAt) return null;

  const start = new Date(injectedAt).getTime();
  const end = analyzedAt ? new Date(analyzedAt).getTime() : now;
  const seconds = Math.max(0, (end - start) / 1000);
  const frozen = Boolean(analyzedAt);
  const underTarget = seconds < 60;

  return (
    <div
      className={clsx(
        'rq-panel flex items-center gap-3 px-4 py-1.5',
        frozen ? (underTarget ? 'rq-panel--ok' : 'rq-panel--warn') : 'rq-panel--quiet',
      )}
    >
      <div className="rq-kicker whitespace-nowrap">Time to root cause</div>
      <div
        className={clsx(
          'rq-stopwatch text-2xl leading-none',
          frozen ? (underTarget ? 'text-ok' : 'text-warn') : 'text-[var(--brand-text)]',
        )}
      >
        {seconds.toFixed(1)}
        <span className="ms-0.5 text-sm font-normal opacity-70">s</span>
      </div>
      {frozen ? (
        <div className={clsx('text-[10px]', underTarget ? 'text-ok' : 'text-warn')}>
          &lt; 60s
        </div>
      ) : (
        <div className="text-[10px] text-[var(--text-3)]">detecting…</div>
      )}
    </div>
  );
}
