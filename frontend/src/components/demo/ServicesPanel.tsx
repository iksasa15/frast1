import { STATUS_COLOR } from '@/lib/colors';
import type { Service } from '@/lib/types';

interface Props {
  services: Service[];
  dnsSuppressed?: boolean;
}

/** Service health list — parent places it (no absolute positioning). */
export function ServicesPanel({ services, dnsSuppressed }: Props) {
  return (
    <div className="rq-panel rq-panel--quiet">
      <div className="rq-slab-title">
        <span>Services</span>
      </div>
      <ul>
        {services.map((s) => {
          const color = STATUS_COLOR[s.status];
          const http = s.metrics?.http_latency_ms;
          const dns = s.metrics?.dns_success_rate;
          const dnsLat = s.metrics?.dns_latency_ms;
          const detail =
            s.id === 'svc-web' && dnsSuppressed
              ? 'via DNS dependency'
              : s.id === 'svc-web' && http != null
                ? `http ${http.toFixed?.(0) ?? http}ms`
                : s.id === 'svc-dns' && dns != null
                  ? `dns ${dns}%${dnsLat != null ? ` · ${Math.round(dnsLat)}ms` : ''}`
                  : s.status;
          return (
            <li
              key={s.id}
              className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-1.5 last:border-b-0"
            >
              <span className="size-1.5 shrink-0" style={{ background: color }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-[var(--text-1)]">{s.label}</div>
                <div className="rq-mono truncate text-[10px] text-[var(--text-3)]">{detail}</div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
