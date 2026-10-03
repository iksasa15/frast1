import { useState } from 'react';
import clsx from 'clsx';
import { FlaskConical, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';

type Check = {
  id: 'agents' | 'ai';
  ok: boolean;
  detail: string;
};

type Result = {
  ok: boolean;
  checks: Check[];
  ms: number;
};

export function AgentsSelfTest({ incidentId }: { incidentId?: string }) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setResult(null);
    const t0 = performance.now();
    const checks: Check[] = [];

    try {
      const agents = await api.agents();
      const n = agents.agents.length;
      const enabled = agents.agents.filter((a) => a.enabled).length;
      const llm = agents.health.llm;
      checks.push({
        id: 'agents',
        ok: n >= 16,
        detail: t('agents.test.agentsDetail', { n, enabled }),
      });

      try {
        const ask = await api.ask(
          i18n.language === 'ar' ? 'ما حالة النظام؟' : 'What is the system status?',
          incidentId,
          i18n.language === 'ar' ? 'ar' : 'en',
        );
        const aiOk = Boolean(ask.answer) && (llm.enabled ? ask.source === 'llm' : ask.source === 'deterministic');
        checks.push({
          id: 'ai',
          ok: aiOk,
          detail: llm.enabled
            ? t('agents.test.aiLlmDetail', {
                source: ask.source,
                provider: llm.provider,
                model: llm.model,
              })
            : t('agents.test.aiOffDetail', { source: ask.source }),
        });
      } catch (e) {
        checks.push({
          id: 'ai',
          ok: false,
          detail: e instanceof Error ? e.message : String(e),
        });
      }
    } catch (e) {
      checks.push({
        id: 'agents',
        ok: false,
        detail: e instanceof Error ? e.message : String(e),
      });
      checks.push({
        id: 'ai',
        ok: false,
        detail: t('agents.test.aiSkipped'),
      });
    }

    setResult({
      ok: checks.every((c) => c.ok),
      checks,
      ms: Math.round(performance.now() - t0),
    });
    setBusy(false);
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        className="rq-btn-secondary inline-flex items-center gap-2 px-3 disabled:opacity-50"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />}
        {busy ? t('agents.test.running') : t('agents.test.button')}
      </button>

      {result && (
        <div
          role="status"
          className={clsx(
            'border px-3 py-2 text-xs',
            result.ok
              ? 'border-[var(--ok)] bg-[var(--ok-soft)] text-[var(--ok)]'
              : 'border-[var(--crit)] bg-[var(--crit-soft)] text-[var(--crit)]',
          )}
        >
          <div className="mb-1.5 flex items-center justify-between gap-2 font-semibold">
            <span>{result.ok ? t('agents.test.pass') : t('agents.test.fail')}</span>
            <span className="rq-mono font-normal opacity-80">{result.ms}ms</span>
          </div>
          <ul className="space-y-1 text-[var(--text-1)]">
            {result.checks.map((c) => (
              <li key={c.id} className="flex items-start gap-2">
                {c.ok ? (
                  <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-[var(--ok)]" />
                ) : (
                  <XCircle size={14} className="mt-0.5 shrink-0 text-[var(--crit)]" />
                )}
                <span>
                  <span className="font-medium">
                    {c.id === 'agents' ? t('agents.test.agentsLabel') : t('agents.test.aiLabel')}:
                  </span>{' '}
                  {c.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
