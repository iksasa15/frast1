import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useOps } from '@/store/useOps';
import { applyLang, type Lang } from '@/lib/theme';
import clsx from 'clsx';

export function TopBar() {
  const { t, i18n } = useTranslation();
  const wsStatus = useOps((s) => s.wsStatus);
  const lastUpdate = useOps((s) => s.lastUpdate);
  const demo = useOps((s) => s.demo);
  const mode = demo?.mode ?? 'live';
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ageSec = lastUpdate ? Math.max(0, Math.round((Date.now() - lastUpdate) / 1000)) : null;
  const dot =
    wsStatus === 'open' ? 'bg-ok' : wsStatus === 'connecting' ? 'bg-warn' : 'bg-crit';

  const toggleLang = () => {
    const next: Lang = i18n.language === 'ar' ? 'en' : 'ar';
    void i18n.changeLanguage(next);
    applyLang(next);
  };

  return (
    <header
      className="flex items-center justify-between border-b border-noc-line bg-noc-panel px-5"
      style={{ height: 'var(--topbar-h)' }}
    >
      <div className="flex items-center gap-4">
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold text-[var(--text-1)]">{t('appName')}</span>
          <span className="rq-kicker !normal-case !tracking-normal">{t('topbar.operations')}</span>
        </div>
        <span className="rq-divider-v h-4" />
        <span className="mode-badge mode-badge--live" title="Live EVE-NG telemetry">
          {mode === 'live' ? t('topbar.live') : t('topbar.sim')}
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs text-[var(--text-2)]">
        <span className="flex items-center gap-2">
          <span className={clsx('inline-block size-1.5', dot)} />
          <bdi className="rq-mono text-[11px]">{wsStatus}</bdi>
        </span>
        <span className="rq-mono text-[11px] text-[var(--text-3)]">
          {ageSec === null ? '—' : t('topbar.lastUpdate', { sec: ageSec })}
        </span>
        <button
          type="button"
          onClick={toggleLang}
          className="border border-[var(--border)] px-2 py-1 text-[10px] text-[var(--text-2)] hover:bg-[var(--bg-hover)]"
        >
          {i18n.language === 'ar' ? 'EN' : 'ع'}
        </button>
      </div>
    </header>
  );
}
