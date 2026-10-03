import { create } from 'zustand';
import type { AgentStep, DemoState, Incident, RawAlert, Topology, WsMessage } from '@/lib/types';
import type { WsStatus } from '@/lib/ws';

type Point = { t: number; util: number; lat: number; loss: number };
export type Selection = { kind: 'node' | 'link' | 'incident'; id: string } | null;

interface OpsState {
  topology: Topology | null;
  linkHistory: Record<string, Point[]>;
  incidents: Record<string, Incident>;
  alerts: RawAlert[];
  agentSteps: AgentStep[];
  demo: DemoState;
  wsStatus: WsStatus;
  lastUpdate: number;
  selection: Selection;
  apply: (m: WsMessage) => void;
  setWs: (s: WsStatus) => void;
  select: (s: Selection) => void;
}

export const useOps = create<OpsState>((set) => ({
  topology: null,
  linkHistory: {},
  incidents: {},
  alerts: [],
  agentSteps: [],
  demo: { mode: 'sim', scenario: null, state: 'idle' },
  wsStatus: 'connecting',
  lastUpdate: 0,
  selection: null,
  setWs: (wsStatus) => set({ wsStatus }),
  select: (selection) => set({ selection }),
  apply: (m) =>
    set((s) => {
      const lastUpdate = Date.now();
      switch (m.type) {
        case 'snapshot':
          return {
            topology: m.data.topology,
            alerts: m.data.alerts,
            // Keep prior demo if a snapshot omits it (avoids undefined → reconnect flicker)
            demo: m.data.demo ?? s.demo,
            lastUpdate,
            incidents: Object.fromEntries(m.data.incidents.map((i) => [i.id, i])),
          };
        case 'link': {
          if (!s.topology) return {};
          const links = s.topology.links.map((l) =>
            l.id === m.data.id ? { ...l, ...m.data } : l,
          );
          const pt = {
            t: m.ts * 1000,
            util: m.data.utilization,
            lat: m.data.latencyMs,
            loss: m.data.packetLoss,
          };
          const hist = [...(s.linkHistory[m.data.id] ?? []), pt].slice(-150);
          return {
            topology: { ...s.topology, links },
            linkHistory: { ...s.linkHistory, [m.data.id]: hist },
            lastUpdate,
          };
        }
        case 'node': {
          if (!s.topology) return {};
          const nodes = s.topology.nodes.map((n) =>
            n.id === m.data.id ? { ...n, ...m.data } : n,
          );
          return { topology: { ...s.topology, nodes }, lastUpdate };
        }
        case 'service': {
          if (!s.topology) return {};
          const services = s.topology.services.map((x) =>
            x.id === m.data.id ? { ...x, ...m.data } : x,
          );
          return { topology: { ...s.topology, services }, lastUpdate };
        }
        case 'alert':
          return { alerts: [m.data, ...s.alerts].slice(0, 200), lastUpdate };
        case 'incident':
          return { incidents: { ...s.incidents, [m.data.id]: m.data }, lastUpdate };
        case 'agent_step':
          return { agentSteps: [...s.agentSteps, m.data].slice(-400), lastUpdate };
        case 'demo':
          return { demo: m.data, lastUpdate };
        case 'topology':
          return { topology: m.data, lastUpdate };
      }
    }),
}));
