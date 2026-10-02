import { useMemo } from 'react';
import { TopologyCanvas } from '@/components/topology/TopologyCanvas';
import { DeviceInspector } from '@/components/topology/DeviceInspector';
import { LinkInspector } from '@/components/topology/LinkInspector';
import { DemoControls } from '@/components/demo/DemoControls';
import { AlertStorm } from '@/components/demo/AlertStorm';
import { MttdStopwatch } from '@/components/demo/MttdStopwatch';
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
  const demo = useOps((s) => s.demo);

  const active = useMemo(() => {
    const list = Object.values(incidents);
    const open = list
      .filter((i) => i.status !== 'resolved')
      .sort((a, b) => b.openedAt.localeCompare(a.openedAt));
    if (open[0]) return open[0];
    if (demo.state === 'recovered') {
      return (
        list
          .filter((i) => i.status === 'resolved')
          .sort((a, b) => (b.resolvedAt ?? '').localeCompare(a.resolvedAt ?? ''))[0] ?? null
      );
    }
    return null;
  }, [incidents, demo.state]);

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

  const showSideInspectors = !active && (selectedNode || selectedLink);

  return (
    <div className="relative h-full w-full">
      {/* Topology stays full-bleed; overlays sit in reserved lanes */}
      <div
        className="absolute inset-0"
        style={{
          // Keep map readable beside the side rails
          paddingInlineStart: 'min(320px, 28vw)',
          paddingInlineEnd: active || showSideInspectors ? 'var(--incident-w)' : 0,
          paddingTop: '3.25rem',
        }}
      >
        <TopologyCanvas
          topology={topology}
          focus={focus}
          onSelect={select}
          onLayoutSaved={(positions) => void api.saveLayout(positions)}
        />
      </div>

      {/* Top dock: simulator + MTTD — clear of side rails */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-40 flex items-start justify-center gap-2 px-3 py-2"
        style={{
          paddingInlineStart: 'calc(min(320px, 28vw) + 8px)',
          paddingInlineEnd: active || showSideInspectors ? 'calc(var(--incident-w) + 8px)' : '12px',
        }}
      >
        <div className="pointer-events-auto flex max-w-full flex-wrap items-start justify-center gap-2">
          <DemoControls />
          <MttdStopwatch
            injectedAt={demo.injectedAt ?? active?.timings.injectedAt}
            analyzedAt={active?.timings.analyzedAt}
          />
        </div>
      </div>

      {/* Start rail: alert analysis + services (stacked, no overlap on map) */}
      <div className="pointer-events-none absolute bottom-2 start-2 top-2 z-20 flex w-[min(300px,26vw)] flex-col gap-2">
        <div className="pointer-events-auto flex min-h-0 flex-1 flex-col gap-2">
          <AlertStorm incident={active} fill />
          <div className="shrink-0">
            <ServicesPanel services={topology.services} dnsSuppressed={dnsSuppressed} />
          </div>
        </div>
      </div>

      {!active && demo.state !== 'recovered' && (
        <div
          className="pointer-events-none absolute top-14 z-10 flex items-center gap-2 border border-[var(--ok)] bg-[var(--ok-soft)] px-3 py-1.5 text-xs text-ok"
          style={{ insetInlineEnd: '12px' }}
        >
          <ShieldCheck className="size-3.5" />
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
