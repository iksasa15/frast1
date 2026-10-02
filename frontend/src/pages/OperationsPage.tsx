import { useMemo } from 'react';
import { TopologyCanvas } from '@/components/topology/TopologyCanvas';
import { DeviceInspector } from '@/components/topology/DeviceInspector';
import { LinkInspector } from '@/components/topology/LinkInspector';
import { AlertStorm } from '@/components/demo/AlertStorm';
import { ServicesPanel } from '@/components/demo/ServicesPanel';
import { IncidentPanel } from '@/components/incidents/IncidentPanel';
import { useOps } from '@/store/useOps';
import { api } from '@/lib/api';
import type { Focus } from '@/components/topology/DeviceNode';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';

export function OperationsPage() {
  const { t } = useTranslation();
  const topology = useOps((s) => s.topology);
  const selection = useOps((s) => s.selection);
  const select = useOps((s) => s.select);
  const incidents = useOps((s) => s.incidents);

  const active = useMemo(() => {
    const list = Object.values(incidents);
    const open = list
      .filter((i) => i.status !== 'resolved')
      .sort((a, b) => b.openedAt.localeCompare(a.openedAt));
    if (open[0]) return open[0];
    return (
      list
        .filter((i) => i.status === 'resolved')
        .sort((a, b) => (b.resolvedAt ?? '').localeCompare(a.resolvedAt ?? ''))[0] ?? null
    );
  }, [incidents]);

  const focus = useMemo(() => {
    const f: Record<string, Focus> = {};
    if (!active) return f;
    if (active.rootCause) {
      f[active.rootCause.entityId] = 'cause';
      for (const id of active.impactPath ?? []) {
        if (id !== active.rootCause.entityId) f[id] = 'impact';
      }
    } else {
      const members = active.members ?? active.evidence.map((e) => e.entityId);
      for (const id of new Set(members)) f[id] = 'impact';
    }
    return f;
  }, [active]);

  const dnsSuppressed = Boolean(
    active?.candidates?.some(
      (c) => c.entityId === 'svc-web' && c.suppressedBy === 'svc-dns',
    ),
  );

  if (!topology) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        Connecting to operations feed…
      </div>
    );
  }

  const selectedNode =
    selection?.kind === 'node' ? topology.nodes.find((n) => n.id === selection.id) : undefined;
  const selectedLink =
    selection?.kind === 'link' ? topology.links.find((l) => l.id === selection.id) : undefined;

  return (
    <div className="relative h-full w-full">
      <TopologyCanvas
        topology={topology}
        focus={focus}
        onSelect={select}
        onLayoutSaved={(positions) => void api.saveLayout(positions)}
      />

      <AlertStorm incident={active} />
      <ServicesPanel services={topology.services} dnsSuppressed={dnsSuppressed} />

      {!active && (
        <div className="pointer-events-none absolute start-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-ok/30 bg-ok/10 px-4 py-2 text-sm text-ok">
          <ShieldCheck className="size-4" />
          {t('incident.empty')}
        </div>
      )}

      <IncidentPanel incident={active} />

      {selectedNode && !active && (
        <DeviceInspector
          device={selectedNode}
          services={topology.services}
          onClose={() => select(null)}
        />
      )}

      {selectedLink && !active && (
        <LinkInspector
          link={selectedLink}
          sourceLabel={
            topology.nodes.find((n) => n.id === selectedLink.source)?.label ?? selectedLink.source
          }
          targetLabel={
            topology.nodes.find((n) => n.id === selectedLink.target)?.label ?? selectedLink.target
          }
          onClose={() => select(null)}
        />
      )}
    </div>
  );
}
