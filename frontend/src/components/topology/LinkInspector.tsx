import { useEffect, useMemo } from 'react';
import type { ReactNode } from 'react';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  ReferenceLine,
  YAxis,
} from 'recharts';
import { X } from 'lucide-react';
import type { TopoLink } from '@/lib/types';
import { STATUS_COLOR } from '@/lib/colors';
import { useOps } from '@/store/useOps';

interface Props {
  link: TopoLink;
  sourceLabel: string;
  targetLabel: string;
  onClose: () => void;
}

export function LinkInspector({ link, sourceLabel, targetLabel, onClose }: Props) {
  const history = useOps((s) => s.linkHistory[link.id] ?? []);

  useEffect(() => {
    void fetch(`/api/links/${link.id}/metrics?minutes=5`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        // Seed history from API if store is empty
        const pts = (data.utilization as [number, number][] | undefined) ?? [];
        if (pts.length === 0) return;
        useOps.setState((s) => {
          if ((s.linkHistory[link.id] ?? []).length > 0) return {};
          const lat = Object.fromEntries((data.latencyMs as [number, number][]) ?? []);
          const loss = Object.fromEntries((data.packetLoss as [number, number][]) ?? []);
          const hist = pts.map(([t, util]) => ({
            t: t * 1000,
            util,
            lat: lat[t] ?? 0,
            loss: loss[t] ?? 0,
          }));
          return { linkHistory: { ...s.linkHistory, [link.id]: hist } };
        });
      })
      .catch(() => undefined);
  }, [link.id]);

  const chartData = useMemo(
    () => history.map((p) => ({ t: p.t, util: p.util, lat: p.lat, loss: p.loss })),
    [history],
  );

  return (
    <aside className="absolute right-0 top-0 z-10 flex h-full w-[360px] flex-col border-l border-noc-line bg-noc-panel/98 shadow-xl">
      <header className="flex items-center justify-between border-b border-noc-line px-4 py-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">Link</div>
          <div className="font-semibold">{link.id}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-white"
        >
          <X size={18} />
        </button>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        <Row label="Endpoints" value={`${sourceLabel} → ${targetLabel}`} />
        <Row label="Ports" value={`${link.sourcePort} ⇄ ${link.targetPort}`} mono />
        <Row label="Role" value={link.role} />
        <Row label="Speed" value={`${link.speedMbps} Mbps`} />
        <Row
          label="Status"
          value={
            <span style={{ color: STATUS_COLOR[link.status] }} className="capitalize">
              {link.status}
            </span>
          }
        />
        <Row label="Utilization" value={`${link.utilization.toFixed(1)}%`} />
        <Row label="Latency" value={`${link.latencyMs.toFixed(1)} ms`} />
        <Row label="Packet loss" value={`${link.packetLoss.toFixed(2)}%`} />

        <Spark title="Utilization %" dataKey="util" data={chartData} refY={85} color="var(--chart-1)" />
        <Spark title="Latency ms" dataKey="lat" data={chartData} color="var(--warn)" />
        <Spark title="Loss %" dataKey="loss" data={chartData} color="var(--crit)" />
      </div>
    </aside>
  );
}

function Spark({
  title,
  dataKey,
  data,
  refY,
  color,
}: {
  title: string;
  dataKey: 'util' | 'lat' | 'loss';
  data: { t: number; util: number; lat: number; loss: number }[];
  refY?: number;
  color: string;
}) {
  return (
    <section>
      <h3 className="mb-1 text-xs uppercase tracking-wider text-slate-500">{title}</h3>
      <div className="h-[60px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <YAxis hide domain={['auto', 'auto']} />
            {refY !== undefined && <ReferenceLine y={refY} stroke="var(--crit)" strokeDasharray="3 3" />}
            <Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className={mono ? 'font-mono text-right' : 'text-right'}>{value}</span>
    </div>
  );
}
