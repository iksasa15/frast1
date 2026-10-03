import type { CSSProperties } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { Router, Network, Server, Radar, Shield } from 'lucide-react';
import clsx from 'clsx';
import type { Iface, Side, TopoNode } from '@/lib/types';
import { STATUS_COLOR, CAUSE_COLOR, IMPACT_COLOR } from '@/lib/colors';
import { zoneBadge, zoneOf } from '@/lib/zones';

export type Focus = 'cause' | 'impact' | null;
export type DeviceNodeT = Node<{ device: TopoNode; focus: Focus }, 'device'>;

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

function shellFor(type: TopoNode['type'], label: string) {
  const isFirewall = /fw|firewall|forti/i.test(label);
  if (type === 'router' && isFirewall) {
    return {
      Icon: Shield,
      className: 'min-w-[152px] rounded-lg px-3 py-2.5',
    };
  }
  if (type === 'router') {
    return {
      Icon: Router,
      // Distinct chassis: wide + soft diamond corners via skew-free rounded diamond feel
      className: 'min-w-[160px] rounded-[1.25rem] px-3 py-2.5',
    };
  }
  if (type === 'switch') {
    return {
      Icon: Network,
      className: 'min-w-[168px] rounded-sm px-3 py-2',
    };
  }
  if (type === 'collector') {
    return {
      Icon: Radar,
      className: 'min-w-[148px] rounded-full px-4 py-2.5',
    };
  }
  return {
    Icon: Server,
    className: 'min-w-[132px] max-w-[148px] rounded-sm px-2.5 py-2',
  };
}

export function DeviceNode({ data, selected }: NodeProps<DeviceNodeT>) {
  const { device, focus } = data;
  const zone = zoneOf(device.zone);
  const shell = shellFor(device.type, device.label);
  const Icon = shell.Icon;
  const bySide = device.interfaces.reduce<Partial<Record<Side, Iface[]>>>((acc, i) => {
    (acc[i.side] ??= []).push(i);
    return acc;
  }, {});

  const statusBorder =
    focus === 'cause' ? CAUSE_COLOR : focus === 'impact' ? IMPACT_COLOR : STATUS_COLOR[device.status];

  return (
    <div
      className={clsx(
        'border bg-noc-panel/95 shadow-md transition-colors',
        shell.className,
        selected && 'ring-2 ring-info ring-offset-1 ring-offset-noc-bg',
        focus === 'cause' && 'rootiq-cause',
        device.type === 'switch' && 'border-t-[3px]',
        device.type === 'server' && 'border-s-[3px]',
      )}
      style={{
        borderColor: statusBorder,
        borderWidth: focus === 'cause' ? 3 : 1,
        borderLeftWidth: zone && focus !== 'cause' ? 3 : undefined,
        borderLeftColor: zone && focus !== 'cause' ? zone.color : undefined,
        borderTopColor: device.type === 'switch' ? zone?.color ?? statusBorder : undefined,
        boxShadow: zone ? `inset 0 0 0 1px ${zone.color}22` : undefined,
      }}
    >
      <div className="flex items-center gap-2">
        <Icon
          className="size-4 shrink-0"
          style={{ color: zone?.color ?? STATUS_COLOR[device.status] }}
          strokeWidth={1.75}
        />
        <span className="truncate text-[13px] font-semibold tracking-wide">{device.label}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[10px] text-slate-400">{device.managementIp}</span>
        {zone && (
          <span
            className="shrink-0 rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider"
            style={{ color: zone.color, background: `${zone.color}18` }}
          >
            {zoneBadge(zone.id)}
          </span>
        )}
      </div>
      {device.type === 'server' && (
        <div className="mt-1.5 flex gap-0.5">
          <span className="h-1 flex-1 rounded-sm bg-slate-600/80" />
          <span className="h-1 flex-1 rounded-sm bg-slate-600/50" />
          <span className="h-1 w-3 rounded-sm" style={{ background: STATUS_COLOR[device.status] }} />
        </div>
      )}
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
