import { NavLink } from 'react-router';
import {
  Network,
  Siren,
  Server,
  Boxes,
  Bot,
  BarChart3,
  ShieldCheck,
  Settings,
} from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { RootIQMark } from '@/components/brand/Logo';

const items: { to: string; labelKey: string; icon: typeof Network; end?: boolean }[] = [
  { to: '/', labelKey: 'nav.topology', icon: Network, end: true },
  { to: '/incidents', labelKey: 'nav.incidents', icon: Siren },
  { to: '/devices', labelKey: 'nav.devices', icon: Server },
  { to: '/services', labelKey: 'nav.services', icon: Boxes },
  { to: '/agents', labelKey: 'nav.agents', icon: Bot },
  { to: '/analytics', labelKey: 'nav.analytics', icon: BarChart3 },
  { to: '/audit', labelKey: 'nav.audit', icon: ShieldCheck },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
];

export function Sidebar() {
  const { t } = useTranslation();
  return (
    <nav
      className="presenter-hide flex h-full flex-col items-center gap-0.5 py-4"
      style={{ width: 'var(--rail-w)' }}
    >
      <div className="mb-6 flex size-10 items-center justify-center border border-[var(--border)] bg-[var(--bg-raised)]">
        <RootIQMark size={28} />
      </div>
      {items.map(({ to, labelKey, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          title={t(labelKey)}
          className={({ isActive }) =>
            clsx(
              'relative flex size-11 items-center justify-center transition-colors',
              isActive
                ? 'bg-[var(--bg-selected)] text-[var(--brand-text)]'
                : 'text-[var(--text-3)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-1)]',
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <span
                  aria-hidden
                  className="absolute inset-y-0 start-0 w-[3px] bg-[var(--brand)]"
                />
              )}
              <Icon size={18} strokeWidth={1.6} />
            </>
          )}
        </NavLink>
      ))}
      <div className="mt-auto pb-2 font-mono text-[9px] tracking-widest text-[var(--text-3)]">
        RQ
      </div>
    </nav>
  );
}
