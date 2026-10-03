import { useState } from 'react';
import clsx from 'clsx';
import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AgentInfo } from '@/lib/types';
import { AUTONOMY_STYLE, LAYER_STYLE, pick } from './agentMeta';

interface Props {
  agent: AgentInfo;
  selected: boolean;
  onToggle: (enabled: boolean) => void;
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] uppercase tracking-wider text-slate-500">{title}</div>
      <ul className="list-disc space-y-0.5 ps-4 text-[11px] text-slate-300">
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

export function AgentCard({ agent, selected, onToggle }: Props) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const [open, setOpen] = useState(false);
  const s = agent.stats;

  return (
    <article
      id={`agent-${agent.id}`}
      className={clsx(
        'flex flex-col gap-2 rounded-lg border bg-noc-panel p-3 transition-colors',
        selected ? 'border-white/50' : 'border-noc-line',
        !agent.enabled && 'opacity-60',
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{pick(ar, agent.name, agent.nameAr)}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className={clsx('rounded border px-1.5 py-0.5 text-[10px] uppercase', LAYER_STYLE[agent.layer])}>
              {t(`agents.layer.${agent.layer}`)}
            </span>
            <span className={clsx('text-[10px] uppercase tracking-wide', AUTONOMY_STYLE[agent.autonomy])}>
              {t(`agents.autonomy.${agent.autonomy}`)}
            </span>
            {agent.usesLlm && (
              <span className="rounded bg-violet-400/15 px-1.5 py-0.5 text-[10px] text-violet-300">LLM ⟡ optional</span>
            )}
          </div>
        </div>
        {agent.canDisable ? (
          <button
            type="button"
            role="switch"
            aria-checked={agent.enabled}
            aria-label={`${agent.name} ${agent.enabled ? t('agents.on') : t('agents.off')}`}
            onClick={() => onToggle(!agent.enabled)}
            className={clsx(
              'relative h-5 w-9 shrink-0 rounded-full transition-colors',
              agent.enabled ? 'bg-ok/70' : 'bg-slate-600',
            )}
          >
            <span
              className={clsx(
                'absolute top-0.5 size-4 rounded-full bg-white transition-all',
                agent.enabled ? 'start-[18px]' : 'start-0.5',
              )}
            />
          </button>
        ) : (
          <span title={t('agents.locked')} className="text-slate-500">
            <Lock size={14} />
          </span>
        )}
      </header>

      <p className="text-xs leading-relaxed text-slate-300">{pick(ar, agent.mission, agent.missionAr)}</p>
      <div className="rounded border border-ok/25 bg-ok/5 px-2 py-1.5 text-[11px] leading-relaxed text-ok/90">
        <span className="font-semibold">{t('agents.benefit')}: </span>
        {pick(ar, agent.benefit, agent.benefitAr)}
      </div>

      <dl className="grid grid-cols-3 gap-2 text-center text-[11px]">
        <div className="rounded bg-noc-bg/60 px-1 py-1">
          <dt className="text-slate-500">{t('agents.runs')}</dt>
          <dd className="font-mono tabular-nums">{s.runs}</dd>
        </div>
        <div className="rounded bg-noc-bg/60 px-1 py-1">
          <dt className="text-slate-500">{t('agents.errors')}</dt>
          <dd className={clsx('font-mono tabular-nums', s.errors > 0 && 'text-crit')}>{s.errors}</dd>
        </div>
        <div className="rounded bg-noc-bg/60 px-1 py-1">
          <dt className="text-slate-500">{t('agents.avgMs')}</dt>
          <dd className="font-mono tabular-nums">{s.avgMs}</dd>
        </div>
      </dl>

      {s.lastSummary && (
        <p className="line-clamp-2 text-[11px] text-slate-500" dir="auto" title={s.lastSummary}>
          {s.lastSummary}
        </p>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="self-start text-[11px] text-info hover:underline"
        aria-expanded={open}
      >
        {open ? t('agents.hideDetails') : t('agents.showDetails')}
      </button>
      {open && (
        <div className="grid gap-2 border-t border-noc-line pt-2 sm:grid-cols-2">
          <List title={t('agents.inputs')} items={agent.inputs} />
          <List title={t('agents.outputs')} items={agent.outputs} />
          <List title={t('agents.tools')} items={agent.tools} />
          <List title={t('agents.needs')} items={agent.needs} />
          <div className="sm:col-span-2">
            <List title={t('agents.guardrails')} items={agent.guardrails} />
          </div>
        </div>
      )}
    </article>
  );
}
