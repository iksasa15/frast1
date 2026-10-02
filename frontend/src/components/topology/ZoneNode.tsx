import type { Node, NodeProps } from '@xyflow/react';
import type { ZoneMeta } from '@/lib/zones';

export type ZoneNodeT = Node<{ zone: ZoneMeta; lang?: string }, 'zone'>;

/** Non-interactive colored panel behind devices in one campus zone. */
export function ZoneNode({ data }: NodeProps<ZoneNodeT>) {
  const { zone, lang } = data;
  const title = lang === 'ar' ? zone.labelAr : zone.label;
  return (
    <div
      className="pointer-events-none h-full w-full border"
      style={{
        background: zone.fill,
        borderColor: zone.border,
        borderRadius: 0,
      }}
    >
      <div
        className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em]"
        style={{ color: zone.color }}
      >
        {title}
      </div>
    </div>
  );
}
