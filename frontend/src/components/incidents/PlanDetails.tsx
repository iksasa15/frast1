import { useState } from 'react';
import clsx from 'clsx';
import type { ActionPlan } from '@/lib/types';
import { VendorCommandsView } from './VendorCommands';

const KIND_STYLE: Record<string, string> = {
  read: 'bg-slate-500/20 text-slate-300',
  change: 'bg-warn/20 text-warn',
  verify: 'bg-ok/20 text-ok',
};

/** The concrete playbook behind a recommendation: steps, blast radius, rollback and success criteria. */
export function PlanDetails({ plan, warnings }: { plan: ActionPlan; warnings?: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded border border-noc-line/70 bg-noc-bg/40 text-[11px]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-2 py-1.5 text-start text-info hover:bg-white/5"
      >
        <span>
          Plan · <span className="font-mono">{plan.playbookId}</span> · {plan.steps.length} steps · rollback ready
        </span>
        <span aria-hidden>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-noc-line/70 px-2 py-2 text-slate-300">
          <ol className="space-y-1">
            {plan.steps.map((s) => (
              <li key={s.n} className="flex gap-1.5">
                <span className={clsx('h-fit shrink-0 rounded px-1 py-0.5 text-[9px] uppercase', KIND_STYLE[s.kind])}>
                  {s.kind}
                </span>
                <span>
                  {s.title}
                  {s.command && <code className="mt-0.5 block break-all text-[10px] text-slate-500">{s.command}</code>}
                </span>
              </li>
            ))}
          </ol>
          <p>
            <span className="text-slate-500">Blast radius: </span>
            {plan.blastRadius}
          </p>
          <div>
            <span className="text-slate-500">Rollback: </span>
            {plan.rollback.map((r) => (
              <span key={r.title}>
                {r.title}
                {r.command && <code className="ms-1 text-[10px] text-slate-500">({r.command})</code>}
              </span>
            ))}
          </div>
          <p>
            <span className="text-slate-500">Success when: </span>
            {plan.verification.map((c) => `${c.metric} ${c.op} ${c.value}`).join(' · ')}
          </p>
          {plan.vendorCommands && <VendorCommandsView vc={plan.vendorCommands} />}
          {[...plan.riskFactors, ...(warnings ?? [])].map((w) => (
            <p key={w} className="text-warn">
              ⚠ {w}
            </p>
          ))}
          <p className="text-slate-500">{plan.labImplementation}</p>
        </div>
      )}
    </div>
  );
}
