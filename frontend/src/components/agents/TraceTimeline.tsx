import { useState } from 'react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type { AgentInfo, AgentStep } from '@/lib/types';
import { LAYER_STYLE, STATUS_STYLE, pick } from './agentMeta';

interface Props {
  steps: AgentStep[];
  agents: AgentInfo[];
}

export function TraceTimeline({ steps, agents }: Props) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const [open, setOpen] = useState<string | null>(null);
  const byId = Object.fromEntries(agents.map((a) => [a.id, a]));

  if (steps.length === 0) {
    return <p className="py-8 text-center text-sm text-slate-500">{t('agents.trace.empty')}</p>;
  }

  const t0 = new Date(steps[0].startedAt).getTime();
  return (
    <ol className="space-y-1.5">
      {steps.map((s) => {
        const a = byId[s.agent];
        const rel = ((new Date(s.startedAt).getTime() - t0) / 1000).toFixed(1);
        const isOpen = open === s.id;
        return (
          <li key={s.id} className="rounded-lg border border-noc-line bg-noc-panel">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : s.id)}
              aria-expanded={isOpen}
              className="flex w-full items-center gap-2 px-3 py-2 text-start"
            >
              <span className="w-12 shrink-0 font-mono text-[11px] tabular-nums text-slate-500">+{rel}s</span>
              <span
                className={clsx(
                  'w-32 shrink-0 truncate rounded border px-1.5 py-0.5 text-[10px]',
                  a ? LAYER_STYLE[a.layer] : 'border-noc-line text-slate-400',
                )}
              >
                {a ? pick(ar, a.name, a.nameAr) : s.agent}
              </span>
              <span className="w-40 shrink-0 truncate font-mono text-[11px] text-slate-300">{s.action}</span>
              <span className={clsx('shrink-0 rounded px-1.5 py-0.5 text-[10px] uppercase', STATUS_STYLE[s.status])}>
                {s.status}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs text-slate-300" dir="auto">
                {s.summary}
              </span>
              <span className="shrink-0 font-mono text-[11px] tabular-nums text-slate-500">{s.durationMs} ms</span>
            </button>
            {isOpen && (
              <div className="border-t border-noc-line px-3 py-2">
                {s.decision && (
                  <p className="mb-1 text-[11px] text-slate-400">
                    {t('agents.trace.decision')}: <span className="font-mono text-info">{s.decision}</span>
                  </p>
                )}
                <pre className="max-h-64 overflow-auto rounded bg-noc-bg/70 p-2 text-[11px] leading-snug text-slate-400" dir="ltr">
                  {JSON.stringify(s.data, null, 2)}
                </pre>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
