import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlaskConical, Play, RotateCcw } from 'lucide-react';
import { api, type Scenario } from '@/lib/api';
import { useOps } from '@/store/useOps';

const SCENARIOS: Scenario[] = ['uplink-congestion', 'dns-failure', 'server-spike'];

/** Compact simulator bar — parent places it (no absolute positioning). */
export function DemoControls() {
  const { t } = useTranslation();
  const demo = useOps((s) => s.demo);
  const [scenario, setScenario] = useState<Scenario>('uplink-congestion');
  const [error, setError] = useState<string | null>(null);
  const busy = (demo?.state ?? 'idle') !== 'idle';

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="rq-panel rq-panel--quiet border border-[var(--border)] bg-[var(--bg-panel)]/95 backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-2 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-2)]">
          <FlaskConical size={13} className="text-[var(--brand)]" />
          {t('demo.title')}
        </span>

        <label className="sr-only" htmlFor="demo-scenario">
          {t('demo.pick')}
        </label>
        <select
          id="demo-scenario"
          value={scenario}
          disabled={busy}
          onChange={(e) => setScenario(e.target.value as Scenario)}
          className="min-w-[10rem] border border-[var(--border)] bg-[var(--bg-canvas)] px-2 py-1 text-xs text-[var(--text-1)] outline-none focus:border-[var(--brand)] disabled:opacity-40"
        >
          {SCENARIOS.map((id) => (
            <option key={id} value={id}>
              {t(`demo.scenario.${id}`)}
            </option>
          ))}
        </select>

        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => api.inject(scenario))}
          className="rq-btn-primary inline-flex h-8 items-center gap-1.5 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={12} />
          {t('demo.run')}
        </button>

        <button
          type="button"
          onClick={() => void run(() => api.reset())}
          className="rq-btn-secondary inline-flex h-8 items-center gap-1.5 px-2.5 text-xs text-[var(--warn)]"
          title={t('demo.reset')}
        >
          <RotateCcw size={12} />
          {t('demo.reset')}
        </button>

        <span className="rq-mono text-[10px] text-[var(--text-3)]">
          {demo?.scenario ? `${demo.scenario} · ${demo.state}` : demo?.state ?? 'idle'}
        </span>
      </div>

      {error && (
        <p className="border-t border-[var(--border-subtle)] px-3 py-1 text-[11px] text-crit">{error}</p>
      )}
    </div>
  );
}
