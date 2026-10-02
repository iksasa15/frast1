import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { Timeline } from '@/components/timeline/Timeline';
import { useOpsSocket } from '@/hooks/useOpsSocket';
import { useHotkeys } from '@/hooks/useHotkeys';
import { useCallback, useEffect, useState } from 'react';
import { useOps } from '@/store/useOps';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';

export function Shell() {
  useOpsSocket();
  const { t } = useTranslation();
  const [presenter, setPresenter] = useState(false);
  const incidents = useOps((s) => s.incidents);
  const wsStatus = useOps((s) => s.wsStatus);

  const onTogglePresenter = useCallback(() => {
    setPresenter((p) => !p);
  }, []);
  useHotkeys(onTogglePresenter);

  useEffect(() => {
    document.documentElement.classList.toggle('presenter-mode', presenter);
    document.documentElement.dataset.presenter = presenter ? 'on' : 'off';
    return () => {
      document.documentElement.classList.remove('presenter-mode');
      document.documentElement.dataset.presenter = 'off';
    };
  }, [presenter]);

  useEffect(() => {
    if (!presenter) {
      document.documentElement.classList.remove('presenter-idle');
      return;
    }
    let timer: number | undefined;
    const bump = () => {
      document.documentElement.classList.remove('presenter-idle');
      window.clearTimeout(timer);
      timer = window.setTimeout(() => document.documentElement.classList.add('presenter-idle'), 3000);
    };
    bump();
    window.addEventListener('mousemove', bump);
    window.addEventListener('keydown', bump);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('mousemove', bump);
      window.removeEventListener('keydown', bump);
      document.documentElement.classList.remove('presenter-idle');
    };
  }, [presenter]);

  useEffect(() => {
    const active = Object.values(incidents).filter((i) => i.status !== 'resolved').length;
    document.title = active > 0 ? `● ${active} incident — RootIQ` : 'RootIQ';
  }, [incidents]);

  return (
    <div
      className={clsx('h-full grid', presenter && 'presenter')}
      style={{
        gridTemplateColumns: presenter ? '0 1fr' : 'var(--rail-w) 1fr',
        gridTemplateRows: 'var(--topbar-h) 1fr var(--timeline-h)',
      }}
    >
      <aside className="row-span-3 border-e border-noc-line bg-noc-panel">
        <Sidebar />
      </aside>

      <TopBar />

      <main className="relative min-h-0 overflow-hidden bg-[var(--bg-canvas)]">
        {wsStatus === 'closed' && (
          <div
            className="absolute inset-x-0 top-0 z-50 border-b px-3 py-1.5 text-center text-xs"
            style={{
              background: 'var(--crit-soft)',
              borderColor: 'var(--crit)',
              color: 'var(--crit)',
            }}
          >
            {t('reconnecting')}
          </div>
        )}
        <Outlet />
      </main>

      <footer className="col-start-2 min-h-0 overflow-hidden border-t border-noc-line bg-noc-panel">
        <Timeline />
      </footer>
    </div>
  );
}
