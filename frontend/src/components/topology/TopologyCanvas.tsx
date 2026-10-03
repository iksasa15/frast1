import { useEffect, useMemo, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ConnectionMode,
  useNodesState,
} from '@xyflow/react';
import { useTranslation } from 'react-i18next';
import { DeviceNode, type Focus } from './DeviceNode';
import { ZoneNode } from './ZoneNode';
import { PortEdge } from './PortEdge';
import { toFlow, type FlowNode } from '@/lib/layout';
import type { Topology } from '@/lib/types';
import { zoneOf } from '@/lib/zones';

const nodeTypes = { device: DeviceNode, zone: ZoneNode };
const edgeTypes = { port: PortEdge };
const NO_FOCUS: Record<string, Focus> = {};

interface Props {
  topology: Topology;
  focus?: Record<string, Focus>;
  onSelect?: (sel: { kind: 'node' | 'link'; id: string } | null) => void;
  onLayoutSaved?: (positions: Record<string, { x: number; y: number }>) => void;
}

export function TopologyCanvas({
  topology,
  focus = NO_FOCUS,
  onSelect,
  onLayoutSaved,
}: Props) {
  const { i18n } = useTranslation();
  const flow = useMemo(
    () => toFlow(topology, focus, i18n.language),
    [topology, focus, i18n.language],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(flow.nodes);

  const layoutKey = useMemo(
    () =>
      topology.nodes
        .map((n) => `${n.id}:${Math.round(n.position.x)}:${Math.round(n.position.y)}`)
        .sort()
        .join('|'),
    [topology.nodes],
  );
  const prevLayoutKey = useRef(layoutKey);

  useEffect(() => {
    const layoutChanged = prevLayoutKey.current !== layoutKey;
    prevLayoutKey.current = layoutKey;
    setNodes((cur) =>
      flow.nodes.map((n) => {
        if (n.type === 'zone' || layoutChanged) return n;
        const prev = cur.find((c) => c.id === n.id);
        return prev ? { ...n, position: prev.position } : n;
      }),
    );
  }, [flow.nodes, layoutKey, setNodes]);

  return (
    <div dir="ltr" className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={flow.edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        connectionMode={ConnectionMode.Loose}
        nodesConnectable={false}
        fitView
        fitViewOptions={{ padding: 0.1, maxZoom: 1.05 }}
        minZoom={0.15}
        maxZoom={2}
        onNodeClick={(_, n) => {
          if (n.type === 'zone') return;
          onSelect?.({ kind: 'node', id: n.id });
        }}
        onEdgeClick={(_, e) => onSelect?.({ kind: 'link', id: e.id })}
        onPaneClick={() => onSelect?.(null)}
        onNodeDragStop={(_, dragged) => {
          if (dragged.type === 'zone') return;
          const devicePositions = Object.fromEntries(
            nodes.filter((n) => n.type === 'device').map((n) => [n.id, n.position]),
          );
          onLayoutSaved?.({
            ...devicePositions,
            [dragged.id]: dragged.position,
          });
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1f2a4d" gap={28} />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          className="!bg-noc-panel !m-2"
          nodeColor={(n) => {
            if (n.type === 'zone') return 'transparent';
            const device = (n.data as { device?: { zone?: string } })?.device;
            return zoneOf(device?.zone)?.color ?? '#64748b';
          }}
        />
        <Controls position="bottom-left" className="!m-2" />
      </ReactFlow>
    </div>
  );
}
