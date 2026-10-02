import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useOps } from '@/store/useOps';
import clsx from 'clsx';

export function TopBar() {
  const { t, i18n } = useTranslation();
  const wsStatus = useOps((s) => s.wsStatus);
  const lastUpdate = useOps((s) => s.lastUpdate);
  const discovery = useOps((s) => s.topology?.discovery);
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ageSec = lastUpdate ? Math.max(0, Math.round((Date.now() - lastUpdate) / 1000)) : null;
  const observedAge = discovery?.observedAt
    ? Math.max(0, Math.round((Date.now() - new Date(discovery.observedAt).getTime()) / 1000))
    : null;
  const discoveryState =
    discovery?.state === 'live' && observedAge != null && observedAge > discovery.staleAfterSeconds
      ? 'degraded'
      : discovery?.state;
  const dot =
    wsStatus === 'open' ? 'bg-ok' : wsStatus === 'connecting' ? 'bg-warn' : 'bg-crit';

  const toggleLang = () => {
    void i18n.changeLanguage(i18n.language === 'ar' ? 'en' : 'ar');
  };

  return (
    <header className="flex items-center justify-between border-b border-noc-line bg-noc-panel px-4">
      <div className="flex items-center gap-3">
        <span className="text-lg font-semibold tracking-wide text-info">{t('appName')}</span>
        <span className="text-xs text-slate-400">{t('topbar.operations')}</span>
        <span
          title={discovery?.errors.join('\n') || 'Live topology discovery status'}
          className={clsx(
            'rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
            discoveryState === 'live' ? 'animate-pulse bg-ok/20 text-ok' :
              discoveryState === 'degraded' ? 'bg-warn/20 text-warn' : 'bg-slate-700 text-slate-300',
          )}
        >
          {discoveryState === 'live' ? t('topbar.live') : discoveryState ?? 'waiting'}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className={clsx('inline-block size-2 rounded-full', dot)} />
          <bdi>{wsStatus}</bdi>
        </span>
        <span>
          {ageSec === null ? '—' : t('topbar.lastUpdate', { sec: ageSec })}
        </span>
        <button
          type="button"
          onClick={toggleLang}
          className="rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-300 hover:bg-white/5"
        >
          {i18n.language === 'ar' ? 'EN' : 'ع'}
        </button>
      </div>
    </header>
  );
}
