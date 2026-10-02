import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { Send, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import type { CopilotAnswer } from '@/lib/types';

interface Msg {
  role: 'user' | 'copilot';
  text: string;
  meta?: CopilotAnswer;
  error?: boolean;
}

interface Props {
  incidentId?: string;
}

const SUGGEST_EN = ['What happened?', 'Why is this the root cause?', 'Why not DNS?', 'What should I do?', 'Which services are affected?', 'Is the collector feed healthy?'];
const SUGGEST_AR = ['ما الذي حدث؟', 'لماذا هذا هو السبب الجذري؟', 'لماذا ليس DNS هو السبب؟', 'ماذا أفعل الآن؟', 'ما الخدمات المتأثرة؟', 'ما هي عتبات الكشف؟'];

export function CopilotPanel({ incidentId }: Props) {
  const { t, i18n } = useTranslation();
  const ar = i18n.language === 'ar';
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [msgs, busy]);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setInput('');
    setMsgs((m) => [...m, { role: 'user', text: question }]);
    setBusy(true);
    try {
      const r = await api.ask(question, incidentId, ar ? 'ar' : undefined);
      setMsgs((m) => [...m, { role: 'copilot', text: r.answer, meta: r }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: 'copilot', text: e instanceof Error ? e.message : String(e), error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-[420px] flex-col rounded-lg border border-noc-line bg-noc-panel">
      <div className="flex items-center gap-2 border-b border-noc-line px-3 py-2 text-[11px] text-ok">
        <ShieldCheck size={14} />
        <span>{t('agents.copilot.readOnly')}</span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {msgs.length === 0 && (
          <div className="space-y-2 py-6 text-center">
            <p className="text-sm text-slate-400">{t('agents.copilot.hint')}</p>
            <div className="flex flex-wrap justify-center gap-1.5">
              {(ar ? SUGGEST_AR : SUGGEST_EN).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void ask(s)}
                  className="rounded-full border border-noc-line px-2.5 py-1 text-xs text-slate-300 hover:bg-white/5"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={clsx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div
              className={clsx(
                'max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed',
                m.role === 'user' ? 'bg-info/20 text-slate-100' : m.error ? 'bg-crit/15 text-crit' : 'bg-noc-bg/70 text-slate-200',
              )}
              dir="auto"
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.meta && (
                <div className="mt-2 space-y-1 border-t border-white/10 pt-1.5 text-[10px] text-slate-500" dir="ltr">
                  <div className="flex flex-wrap gap-x-2">
                    <span>{m.meta.intent}</span>
                    <span>· {t('agents.copilot.confidence')}: {m.meta.confidence}</span>
                    <span>· {m.meta.source === 'llm' ? 'LLM (grounded)' : t('agents.copilot.deterministic')}</span>
                  </div>
                  {m.meta.sources.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {m.meta.sources.map((s) => (
                        <span key={`${s.n}-${s.source}`} className="rounded bg-white/5 px-1.5 py-0.5 font-mono" title={s.title}>
                          [{s.n}] {s.source}
                        </span>
                      ))}
                    </div>
                  )}
                  {m.meta.warnings.map((w) => (
                    <div key={w} className="text-warn" dir="auto">
                      ⚠ {w}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <p className="text-xs text-slate-500">{t('agents.copilot.thinking')}</p>}
        <div ref={endRef} />
      </div>

      <form
        className="flex items-center gap-2 border-t border-noc-line p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('agents.copilot.placeholder')}
          maxLength={1000}
          dir="auto"
          aria-label={t('agents.copilot.placeholder')}
          className="min-w-0 flex-1 rounded-lg border border-noc-line bg-noc-bg px-3 py-2 text-sm outline-none focus:border-info"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label={t('agents.copilot.send')}
          className="rounded-lg bg-info/80 p-2 text-black hover:bg-info disabled:opacity-40"
        >
          <Send size={16} className="rtl:-scale-x-100" />
        </button>
      </form>
    </div>
  );
}
