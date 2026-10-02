import type { CSSProperties } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { Router, Network, Server, Radar } from 'lucide-react';
import clsx from 'clsx';
import type { Iface, Side, TopoNode } from '@/lib/types';
import { STATUS_COLOR, CAUSE_COLOR, IMPACT_COLOR } from '@/lib/colors';
import { zoneOf } from '@/lib/zones';

export type Focus = 'cause' | 'impact' | null;
export type DeviceNodeT = Node<{ device: TopoNode; focus: Focus }, 'device'>;

const ICON = { router: Router, switch: Network, server: Server, collector: Radar } as const;
const POS: Record<Side, Position> = {
  top: Position.Top,
  bottom: Position.Bottom,
  left: Position.Left,
  right: Position.Right,
};

function handleStyle(side: Side, idx: number, total: number): CSSProperties {
  const pct = `${((idx + 1) / (total + 1)) * 100}%`;
  return side === 'top' || side === 'bottom' ? { left: pct } : { top: pct };
}

export function DeviceNode({ data, selected }: NodeProps<DeviceNodeT>) {
  const { device, focus } = data;
  const Icon = ICON[device.type];
  const zone = zoneOf(device.zone);
  const bySide = device.interfaces.reduce<Partial<Record<Side, Iface[]>>>((acc, i) => {
    (acc[i.side] ??= []).push(i);
    return acc;
  }, {});

  const statusBorder =
    focus === 'cause' ? CAUSE_COLOR : focus === 'impact' ? IMPACT_COLOR : STATUS_COLOR[device.status];

  return (
    <div
      className={clsx(
        'min-w-[148px] border bg-noc-panel px-3 py-2.5 transition-colors',
        selected && 'outline outline-1 outline-[var(--brand)] outline-offset-2',
        focus === 'cause' && 'rootiq-cause',
      )}
      style={{
        borderColor: statusBorder,
        borderWidth: focus === 'cause' ? 3 : 1,
        borderRadius: 0,
        borderLeftWidth: zone && focus !== 'cause' ? 3 : undefined,
        borderLeftColor: zone && focus !== 'cause' ? zone.color : undefined,
        boxShadow: zone ? `inset 0 0 0 1px ${zone.color}22` : undefined,
      }}
    >
      <div className="flex items-center gap-2">
        <Icon
          className="size-5"
          style={{ color: zone?.color ?? STATUS_COLOR[device.status] }}
          strokeWidth={1.75}
        />
        <span className="font-semibold tracking-wide">{device.label}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-[var(--text-3)]">{device.managementIp}</span>
        {zone && (
          <span
            className="shrink-0 text-[9px] font-semibold uppercase tracking-wider"
            style={{ color: zone.color }}
          >
            {zone.id === 'building-a'
              ? 'A'
              : zone.id === 'building-b'
                ? 'B'
                : zone.id === 'datacenter'
                  ? 'DC'
                  : zone.id === 'demo'
                    ? 'LAB'
                    : zone.id === 'edge'
                      ? 'EDGE'
                      : 'CORE'}
          </span>
        )}
      </div>
      {(Object.keys(bySide) as Side[]).flatMap((side) =>
        (bySide[side] ?? []).map((i, idx) => (
          <Handle
            key={i.name}
            id={i.name}
            type="source"
            position={POS[side]}
            style={handleStyle(side, idx, bySide[side]!.length)}
            className="!size-2.5 !border-0 !bg-slate-300"
            title={i.name}
          />
        )),
      )}
    </div>
  );
}
