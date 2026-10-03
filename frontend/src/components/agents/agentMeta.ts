import type { AgentInfo, AgentStep } from '@/lib/types';

export const LAYER_STYLE: Record<AgentInfo['layer'], string> = {
  supervisor: 'bg-info/15 text-info border-info/40',
  perception: 'bg-ok/15 text-ok border-ok/40',
  reasoning: 'bg-degraded/15 text-degraded border-degraded/40',
  knowledge: 'bg-violet-400/15 text-violet-300 border-violet-400/40',
  governance: 'bg-crit/15 text-crit border-crit/40',
  action: 'bg-warn/15 text-warn border-warn/40',
  learning: 'bg-teal-400/15 text-teal-300 border-teal-400/40',
};

export const STATUS_STYLE: Record<AgentStep['status'], string> = {
  ok: 'bg-ok/15 text-ok',
  skipped: 'bg-slate-500/20 text-slate-400',
  error: 'bg-crit/20 text-crit',
  denied: 'bg-crit/20 text-crit',
};

export const AUTONOMY_STYLE: Record<AgentInfo['autonomy'], string> = {
  observe: 'text-slate-400',
  advise: 'text-info',
  coordinate: 'text-violet-300',
  act_with_approval: 'text-warn',
};

export function pick(ar: boolean, en: string, arText: string): string {
  return ar ? arText : en;
}
