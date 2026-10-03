import { STATUS_COLOR } from '@/lib/colors';
import type { Service } from '@/lib/types';

interface Props {
  services: Service[];
  dnsSuppressed?: boolean;
}

export function ServicesPanel({ services, dnsSuppressed }: Props) {
  return (
    <div className="pointer-events-auto absolute bottom-14 start-3 z-20 max-h-[40%] w-56 overflow-y-auto rounded-xl border border-noc-line bg-noc-panel/95 p-3 shadow-xl">
      <div className="mb-2 text-[10px] uppercase tracking-wider text-slate-500">Services</div>
      <ul className="space-y-2">
        {services.map((s) => {
          const color = STATUS_COLOR[s.status];
          const http = s.metrics?.http_latency_ms;
          const dns = s.metrics?.dns_success_rate;
          const dnsLat = s.metrics?.dns_latency_ms;
          const detail =
            s.id === 'svc-web' && dnsSuppressed
              ? 'impacted via DNS dependency'
              : s.id === 'svc-web' && http != null
                ? `http ${http.toFixed?.(0) ?? http}ms`
                : s.id === 'svc-dns' && dns != null
                  ? `dns ${dns}%${dnsLat != null ? ` · ${Math.round(dnsLat)}ms` : ''}`
                  : s.status;
          return (
            <li
              key={s.id}
              className="rounded-lg border px-2 py-1.5"
              style={{ borderColor: `${color}55` }}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium">{s.label}</span>
                <span className="size-2 rounded-full" style={{ background: color }} />
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-slate-400">{detail}</div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
