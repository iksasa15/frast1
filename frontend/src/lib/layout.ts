import type { DeviceNodeT, Focus } from '@/components/topology/DeviceNode';
import type { PortEdgeT } from '@/components/topology/PortEdge';
import type { ZoneNodeT } from '@/components/topology/ZoneNode';
import type { Topology } from './types';
import { ZONES, type ZoneId, zoneOf } from './zones';

const PAD_X = 48;
const PAD_Y_TOP = 44;
const PAD_Y_BOTTOM = 32;
const NODE_W = 168;
const NODE_H = 78;

export type FlowNode = DeviceNodeT | ZoneNodeT;

function zonePanels(t: Topology, lang?: string): ZoneNodeT[] {
  const byZone = new Map<ZoneId, { minX: number; minY: number; maxX: number; maxY: number }>();
  for (const n of t.nodes) {
    const z = zoneOf(n.zone);
    if (!z) continue;
    const box = byZone.get(z.id) ?? {
      minX: n.position.x,
      minY: n.position.y,
      maxX: n.position.x,
      maxY: n.position.y,
    };
    box.minX = Math.min(box.minX, n.position.x);
    box.minY = Math.min(box.minY, n.position.y);
    box.maxX = Math.max(box.maxX, n.position.x);
    box.maxY = Math.max(box.maxY, n.position.y);
    byZone.set(z.id, box);
  }

  return [...byZone.entries()].map(([id, box]) => {
    const zone = ZONES[id];
    const x = box.minX - PAD_X;
    const y = box.minY - PAD_Y_TOP;
    const width = box.maxX - box.minX + NODE_W + PAD_X * 2;
    const height = box.maxY - box.minY + NODE_H + PAD_Y_TOP + PAD_Y_BOTTOM;
    return {
      id: `zone:${id}`,
      type: 'zone' as const,
      position: { x, y },
      data: { zone, lang },
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: -1,
      style: { width, height },
    };
  });
}

export function toFlow(t: Topology, focus: Record<string, Focus> = {}, lang?: string) {
  const devices: DeviceNodeT[] = t.nodes.map((n) => ({
    id: n.id,
    type: 'device',
    position: n.position,
    zIndex: 1,
    data: { device: n, focus: focus[n.id] ?? null },
  }));
  const nodes: FlowNode[] = [...zonePanels(t, lang), ...devices];
  const edges: PortEdgeT[] = t.links.map((l) => ({
    id: l.id,
    type: 'port',
    source: l.source,
    target: l.target,
    sourceHandle: l.sourcePort,
    targetHandle: l.targetPort,
    data: { link: l, focus: focus[l.id] ?? null },
  }));
  return { nodes, edges };
}
