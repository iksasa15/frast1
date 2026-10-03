import { useState } from 'react';
import type { ConfigModel, VendorCommands, VendorDiagnose } from '@/lib/types';

const STYLE_LABEL: Record<ConfigModel['style'], string> = {
  'running-startup': 'running → startup (save separately)',
  'candidate-commit': 'candidate → commit',
  'auto-save': 'applied and saved immediately',
};

function Cmds({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <p className="text-slate-400">
      {label}{' '}
      {items.map((c) => (
        <code key={c} className="me-1 break-all text-[10px] text-info">
          {c}
        </code>
      ))}
    </p>
  );
}

/** How a change is applied and saved on this device: the part that differs most between vendors. */
function ConfigBlock({ cm }: { cm: ConfigModel }) {
  return (
    <div className="mt-1 rounded border border-noc-line/50 px-1.5 py-1" data-testid="config-model">
      <p className="text-slate-300">
        Applying a change: <span className="text-warn">{STYLE_LABEL[cm.style]}</span>
      </p>
      <p className="text-slate-500">{cm.summary}</p>
      <Cmds label="Enter config:" items={cm.enter} />
      <Cmds label="Save / activate:" items={cm.save} />
      <Cmds label="Restore point:" items={cm.snapshot} />
      <Cmds label="Safer change:" items={cm.safeChange} />
      <Cmds label="Roll back:" items={cm.rollback} />
      {cm.cliStyle && <p className="text-slate-500">CLI style: {cm.cliStyle}</p>}
    </div>
  );
}

function DeviceBlock({ d, label, cm }: { d: VendorDiagnose; label: string; cm?: ConfigModel | null }) {
  const usable = d.checks.filter((c) => c.available);
  return (
    <div className="rounded border border-noc-line/60 px-2 py-1.5">
      <p className="text-slate-300">
        <span className="font-semibold">{label}</span>
        {d.interface && <span className="ms-1 font-mono text-[10px] text-slate-500">{d.interface}</span>}
        <span className="ms-2 text-slate-500">
          {d.vendor ? `${d.vendor}${d.os ? ` / ${d.os}` : ''}` : 'vendor not identified'}
        </span>
      </p>
      {usable.length === 0 && <p className="text-slate-500">{d.note || 'No curated commands for this vendor yet.'}</p>}
      <ul className="mt-1 space-y-1">
        {usable.map((c) => (
          <li key={c.capability}>
            <span className="text-slate-500">{c.why}</span>
            {c.commands.map((cmd) => (
              <code key={cmd} className="block break-all text-[10px] text-info">
                {cmd}
              </code>
            ))}
          </li>
        ))}
      </ul>
      {cm && <ConfigBlock cm={cm} />}
    </div>
  );
}

/** Vendor-specific reference commands for the devices involved. Read-only; RootIQ does not run them. */
export function VendorCommandsView({ vc }: { vc: VendorCommands }) {
  const [open, setOpen] = useState(false);
  const byId = Object.fromEntries(vc.devices.map((d) => [d.id, d]));
  return (
    <div className="rounded border border-noc-line/60 bg-noc-bg/30" data-testid="vendor-commands">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-2 py-1 text-start text-violet-300 hover:bg-white/5"
      >
        <span>
          Vendor diagnostics · {vc.title} · {vc.diagnose.length} device(s)
        </span>
        <span aria-hidden>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-noc-line/60 px-2 py-2">
          {vc.diagnose.map((d) => (
            <DeviceBlock key={d.device} d={d} label={byId[d.device]?.label ?? d.device} cm={byId[d.device]?.configModel} />
          ))}
          {vc.fixes
            .filter((f) => f.commands.length > 0)
            .map((f) => (
              <p key={f.id} className="text-warn">
                Fix option (needs approval): {f.title}
              </p>
            ))}
          <p className="text-slate-500">{vc.note}</p>
        </div>
      )}
    </div>
  );
}
