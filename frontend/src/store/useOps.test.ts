import { useOps } from './useOps';
import type { AgentStep } from '@/lib/types';

const step = (id: string): AgentStep => ({
  id,
  agent: 'rca',
  action: 'rank_causes',
  incidentId: 'INC-1',
  status: 'ok',
  startedAt: '2026-01-01T00:00:00Z',
  durationMs: 1,
  summary: 'top cause',
  data: {},
  decision: null,
});

test('agent_step messages are appended in order and capped at 400', () => {
  useOps.setState({ agentSteps: [] });
  for (let i = 0; i < 450; i++) {
    useOps.getState().apply({ type: 'agent_step', ts: i, data: step(`AS-${i}`) });
  }
  const steps = useOps.getState().agentSteps;
  expect(steps).toHaveLength(400);
  expect(steps[0].id).toBe('AS-50');
  expect(steps[steps.length - 1].id).toBe('AS-449');
});
