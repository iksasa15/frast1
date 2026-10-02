import type { AgentInfo, AgentsResponse, AgentStep, CopilotAnswer, DemoState, Incident, Topology } from './types';

async function j<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    headers: { 'content-type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export type Scenario = 'uplink-congestion' | 'dns-failure' | 'server-spike';

export const api = {
  topology: () => j<Topology>('/api/topology'),
  saveLayout: (positions: Record<string, { x: number; y: number }>) =>
    j('/api/topology/layout', { method: 'PUT', body: JSON.stringify({ positions }) }),
  linkMetrics: (id: string) =>
    j<Record<string, [number, number][]>>(`/api/links/${id}/metrics?minutes=5`),
  incidents: () => j<Incident[]>('/api/incidents'),
  inject: (s: Scenario) => j<DemoState>(`/api/demo/inject/${s}`, { method: 'POST' }),
  reset: () => j<DemoState>('/api/demo/reset', { method: 'POST' }),
  setMode: (mode: 'live' | 'sim') =>
    j<DemoState>('/api/demo/mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  incidentReplay: (id: string) =>
    j<{ incidentId: string; steps: Array<{ ts: number; kind: string; label: string; entityId?: string; value?: number }> }>(
      `/api/incidents/${id}/replay`,
    ),
  runs: () =>
    j<{
      runs: unknown[];
      summary: {
        count: number;
        top1Accuracy: number | null;
        avgTimeToRootCause: number | null;
        avgNoiseReduction: number | null;
      };
    }>('/api/runs'),
  agents: () => j<AgentsResponse>('/api/agents'),
  agentTrace: (incidentId?: string, limit = 300) =>
    j<AgentStep[]>(`/api/agents/trace?limit=${limit}${incidentId ? `&incidentId=${incidentId}` : ''}`),
  toggleAgent: (id: string, enabled: boolean, actor: string) =>
    j<AgentInfo>(`/api/agents/${id}/toggle`, { method: 'POST', body: JSON.stringify({ enabled, actor }) }),
  ask: (question: string, incidentId?: string, lang?: 'ar' | 'en') =>
    j<CopilotAnswer>('/api/copilot/ask', {
      method: 'POST',
      body: JSON.stringify({ question, incidentId: incidentId ?? null, lang: lang ?? null }),
    }),
  acknowledge: (incidentId: string, by: string) =>
    j<Incident>(`/api/incidents/${incidentId}/acknowledge`, { method: 'POST', body: JSON.stringify({ by }) }),
  postmortem: (incidentId: string) =>
    j<{ markdown: string; improvements: string[] }>(`/api/incidents/${incidentId}/postmortem`),
  approve: (actionId: string, decidedBy: string) =>
    j(`/api/actions/${actionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ decidedBy }),
    }),
  reject: (actionId: string, decidedBy: string, reason: string) =>
    j(`/api/actions/${actionId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ decidedBy, reason }),
    }),
};
