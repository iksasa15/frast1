import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlaskConical, Play, RotateCcw } from 'lucide-react';
import { api, type Scenario } from '@/lib/api';
import { useOps } from '@/store/useOps';

const SCENARIOS: Scenario[] = ['uplink-congestion', 'dns-failure', 'server-spike'];

/** Compact simulator bar for offline campus demos. */
export function DemoControls() {
  const { t } = useTranslation();
  const demo = useOps((s) => s.demo);
  const [scenario, setScenario] = useState<Scenario>('uplink-congestion');
  const [error, setError] = useState<string | null>(null);
  const busy = demo.state !== 'idle';

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="absolute end-3 top-3 z-30 max-w-[min(100%-1.5rem,28rem)] rounded-lg border border-noc-line bg-noc-panel/95 text-xs shadow-lg backdrop-blur-sm">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-wider text-slate-400">
          <FlaskConical size={13} className="text-info" />
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
          className="min-w-[10rem] rounded border border-noc-line bg-noc-bg px-2 py-1.5 text-slate-200 outline-none focus:border-info disabled:opacity-40"
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
          className="inline-flex items-center gap-1.5 rounded bg-info px-3 py-1.5 font-semibold text-black disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={12} />
          {t('demo.run')}
        </button>

        <button
          type="button"
          onClick={() => void run(() => api.reset())}
          className="inline-flex items-center gap-1.5 rounded border border-warn/40 px-2.5 py-1.5 text-warn hover:bg-warn/10"
          title={t('demo.reset')}
        >
          <RotateCcw size={12} />
          {t('demo.reset')}
        </button>

        <span className="font-mono text-[10px] text-slate-500">
          {demo.scenario ? `${demo.scenario} · ${demo.state}` : demo.state}
        </span>
      </div>

      {error && (
        <p className="border-t border-noc-line px-3 py-1.5 text-[11px] text-crit">{error}</p>
      )}
    </div>
  );
}
