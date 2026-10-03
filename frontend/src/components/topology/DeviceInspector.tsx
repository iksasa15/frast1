import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Service, TopoNode } from '@/lib/types';
import { STATUS_COLOR } from '@/lib/colors';
import { zoneOf } from '@/lib/zones';
import { X } from 'lucide-react';

interface Props {
  device: TopoNode;
  services: Service[];
  onClose: () => void;
}

export function DeviceInspector({ device, services, onClose }: Props) {
  const { i18n } = useTranslation();
  const hosted = services.filter((s) => s.host === device.id);
  const zone = zoneOf(device.zone);

  return (
    <aside className="absolute right-0 top-0 z-10 flex h-full w-[360px] flex-col border-l border-noc-line bg-noc-panel/98 shadow-xl">
      <header className="flex items-center justify-between border-b border-noc-line px-4 py-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500">{device.type}</div>
          <div className="font-semibold">{device.label}</div>
        </div>
        <button type="button" onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-white">
          <X size={18} />
        </button>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        <Row label="Vendor" value={device.vendor ?? '—'} />
        <Row label="Management IP" value={device.managementIp} mono />
        {zone && (
          <Row
            label="Building / Zone"
            value={
              <span className="inline-flex items-center gap-1.5" style={{ color: zone.color }}>
                <span className="inline-block size-2.5 rounded-sm" style={{ background: zone.color }} />
                {i18n.language === 'ar' ? zone.labelAr : zone.label}
              </span>
            }
          />
        )}
        <Row
          label="Status"
          value={
            <span style={{ color: STATUS_COLOR[device.status] }} className="capitalize">
              {device.status}
            </span>
          }
        />

        {(device.metrics?.cpu_percent != null || device.metrics?.mem_percent != null) && (
          <section>
            <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Live metrics</h3>
            <div className="space-y-2">
              {device.metrics.cpu_percent != null && (
                <MetricBar label="CPU" value={device.metrics.cpu_percent} />
              )}
              {device.metrics.mem_percent != null && (
                <MetricBar label="Mem" value={device.metrics.mem_percent} />
              )}
            </div>
          </section>
        )}

        <section>
          <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Interfaces</h3>
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="pb-1 font-normal">Name</th>
                <th className="pb-1 font-normal">Side</th>
                <th className="pb-1 font-normal">Speed</th>
                <th className="pb-1 font-normal">State</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {device.interfaces.map((i) => (
                <tr key={i.name} className="border-t border-noc-line/60">
                  <td className="py-1.5">{i.name}</td>
                  <td className="py-1.5 text-slate-400">{i.side}</td>
                  <td className="py-1.5">{i.speedMbps}</td>
                  <td className="py-1.5 capitalize">{i.operState ?? 'up'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Hosted services</h3>
          {hosted.length === 0 ? (
            <p className="text-slate-500">None</p>
          ) : (
            <ul className="space-y-1">
              {hosted.map((s) => (
                <li key={s.id} className="flex justify-between">
                  <span>{s.label}</span>
                  <span className="font-mono text-slate-400">:{s.port}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </aside>
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

function MetricBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-mono tabular-nums">{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-noc-bg">
        <div
          className="h-full rounded bg-info transition-[width]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
