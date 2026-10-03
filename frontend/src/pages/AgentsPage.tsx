import { useCallback, useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import type { AgentInfo, AgentStep, AgentsResponse } from '@/lib/types';
import { useOps } from '@/store/useOps';
import { AgentCard } from '@/components/agents/AgentCard';
import { CopilotPanel } from '@/components/agents/CopilotPanel';
import { FlowDiagram } from '@/components/agents/FlowDiagram';
import { TraceTimeline } from '@/components/agents/TraceTimeline';
import { AgentsSelfTest } from '@/components/agents/AgentsSelfTest';

type Tab = 'overview' | 'trace' | 'copilot';
const TABS: Tab[] = ['overview', 'trace', 'copilot'];

export function AgentsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('overview');
  const [data, setData] = useState<AgentsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [incidentFilter, setIncidentFilter] = useState<string>('');
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const incidents = useOps((s) => s.incidents);
  const liveSteps = useOps((s) => s.agentSteps.length);

  const loadAgents = useCallback(() => {
    api
      .agents()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    loadAgents();
    const id = setInterval(loadAgents, 4000);
    return () => clearInterval(id);
  }, [loadAgents]);

  const incidentList = useMemo(
    () => Object.values(incidents).sort((a, b) => new Date(b.openedAt).getTime() - new Date(a.openedAt).getTime()),
    [incidents],
  );
  const activeIncident = incidentList.find((i) => i.status !== 'resolved') ?? incidentList[0];

  useEffect(() => {
    if (tab !== 'trace') return;
    let cancelled = false;
    api
      .agentTrace(incidentFilter || undefined)
      .then((s) => !cancelled && setSteps(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tab, incidentFilter, liveSteps]);

  const toggle = (agent: AgentInfo, enabled: boolean) => {
    const actor = localStorage.getItem('rootiq.engineer') || 'Ahmed';
    api
      .toggleAgent(agent.id, enabled, actor)
      .then(loadAgents)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };

  const selectAgent = (id: string) => {
    setSelected(id);
    document.getElementById(`agent-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const h = data?.health;
  return (
    <div className="h-full overflow-y-auto p-4">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div>
            <h1 className="text-lg font-semibold tracking-wide">{t('agents.title')}</h1>
            <p className="text-xs text-slate-400">{t('agents.subtitle', { n: data?.agents.length ?? 16 })}</p>
          </div>
          <AgentsSelfTest incidentId={activeIncident?.id} />
        </div>
        {h && (
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className={clsx('rounded border px-2 py-1', h.llm.enabled ? 'border-violet-400/40 text-violet-300' : 'border-noc-line text-slate-400')}>
              {h.llm.enabled ? t('agents.llmOn', { provider: h.llm.provider, model: h.llm.model }) : t('agents.llmOff')}
            </span>
            <span className="rounded border border-noc-line px-2 py-1 text-slate-400">
              {t('agents.kb', { n: h.knowledge.chunks })}
            </span>
            {h.vendors && (
              <span className="rounded border border-noc-line px-2 py-1 text-slate-400">
                {t('agents.vendors', { n: h.vendors.vendors, full: h.vendors.coverage.full })}
              </span>
            )}
            <span className="rounded border border-noc-line px-2 py-1 text-slate-400">
              {t('agents.dataQuality', { pct: Math.round(h.telemetry.qualityScore * 100) })}
            </span>
          </div>
        )}
      </header>

      <div role="tablist" className="mb-4 flex gap-1 border-b border-noc-line">
        {TABS.map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            type="button"
            onClick={() => setTab(k)}
            className={clsx(
              '-mb-px border-b-2 px-3 py-2 text-sm transition-colors',
              tab === k ? 'border-info text-info' : 'border-transparent text-slate-400 hover:text-slate-200',
            )}
          >
            {t(`agents.tab.${k}`)}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded border border-crit/40 bg-crit/10 px-3 py-2 text-xs text-crit">
          {error}
        </div>
      )}
      {!data && !error && <p className="text-sm text-slate-500">{t('agents.loading')}</p>}

      {data && tab === 'overview' && (
        <div className="space-y-5">
          <section className="rounded-lg border border-noc-line bg-noc-panel p-3">
            <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">{t('agents.flow.title')}</h2>
            <FlowDiagram flow={data.flow} agents={data.agents} activeAgent={selected} onSelect={selectAgent} />
          </section>
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.agents.map((a) => (
              <AgentCard key={a.id} agent={a} selected={selected === a.id} onToggle={(en) => toggle(a, en)} />
            ))}
          </section>
        </div>
      )}

      {data && tab === 'trace' && (
        <section>
          <div className="mb-3 flex items-center gap-2 text-xs">
            <label htmlFor="trace-incident" className="text-slate-400">
              {t('agents.trace.incident')}
            </label>
            <select
              id="trace-incident"
              value={incidentFilter}
              onChange={(e) => setIncidentFilter(e.target.value)}
              className="rounded border border-noc-line bg-noc-bg px-2 py-1 text-slate-200"
            >
              <option value="">{t('agents.trace.all')}</option>
              {incidentList.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.id} · {i.title}
                </option>
              ))}
            </select>
            <span className="text-slate-500">{t('agents.trace.count', { n: steps.length })}</span>
          </div>
          <TraceTimeline steps={steps} agents={data.agents} />
        </section>
      )}

      {tab === 'copilot' && (
        <section className="grid gap-3 lg:grid-cols-[1fr_320px]">
          <CopilotPanel incidentId={activeIncident?.id} />
          <aside className="space-y-2 rounded-lg border border-noc-line bg-noc-panel p-3 text-xs text-slate-400">
            <h2 className="text-xs uppercase tracking-wider text-slate-500">{t('agents.copilot.context')}</h2>
            <p>
              {activeIncident
                ? t('agents.copilot.aboutIncident', { id: activeIncident.id })
                : t('agents.copilot.noIncident')}
            </p>
            <p>{t('agents.copilot.howItWorks')}</p>
          </aside>
        </section>
      )}
    </div>
  );
}
