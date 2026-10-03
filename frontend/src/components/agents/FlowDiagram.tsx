import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type { AgentInfo, AgentsResponse } from '@/lib/types';
import { LAYER_STYLE, pick } from './agentMeta';

interface Props {
  flow: AgentsResponse['flow'];
  agents: AgentInfo[];
  activeAgent?: string | null;
  onSelect: (id: string) => void;
}

/** The investigation pipeline as columns; the human decision is a fixed, highlighted gate. */
export function FlowDiagram({ flow, agents, activeAgent, onSelect }: Props) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const byId = Object.fromEntries(agents.map((a) => [a.id, a]));

  return (
    <div className="overflow-x-auto pb-1">
      <div className="flex min-w-[860px] items-stretch gap-2">
        {flow.stages.map((stage, i) => {
          const human = stage.stage === 'human';
          return (
            <div key={`${stage.stage}-${i}`} className="flex flex-1 items-stretch gap-2">
              <div
                className={clsx(
                  'flex flex-1 flex-col gap-1.5 rounded-lg border p-2',
                  human
                    ? 'items-center justify-center border-ok/60 bg-ok/10 text-center'
                    : 'border-noc-line bg-noc-bg/40',
                )}
              >
                <div className={clsx('text-[10px] uppercase tracking-wider', human ? 'text-ok' : 'text-slate-500')}>
                  {t(`agents.stage.${stage.stage}`)}
                </div>
                {human ? (
                  <div className="text-xs font-semibold text-ok">{t('agents.human')}</div>
                ) : (
                  stage.agents.map((id) => {
                    const a = byId[id];
                    if (!a) return null;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => onSelect(id)}
                        className={clsx(
                          'rounded border px-2 py-1 text-start text-[11px] transition-colors hover:brightness-125',
                          LAYER_STYLE[a.layer],
                          !a.enabled && 'opacity-40 line-through',
                          activeAgent === id && 'ring-1 ring-white/60',
                        )}
                      >
                        {pick(ar, a.name, a.nameAr)}
                      </button>
                    );
                  })
                )}
              </div>
              {i < flow.stages.length - 1 && (
                <div className="flex items-center text-slate-600 rtl:rotate-180">›</div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-slate-500">{t('agents.flowNote')}</p>
    </div>
  );
}
