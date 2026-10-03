import { useState } from 'react';
import type { Action } from '@/lib/types';
import clsx from 'clsx';
import { api } from '@/lib/api';
import { useTranslation } from 'react-i18next';
import { RejectDialog } from './RejectDialog';
import { PlanDetails } from './PlanDetails';

interface Props {
  action: Action & { alternatives?: string[]; scenario?: string };
  engineer: string;
  incidentStatus: string;
  needsInvestigation?: boolean;
}

export function ActionCard({ action, engineer, incidentStatus, needsInvestigation }: Props) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const riskColor =
    action.riskLevel === 'low'
      ? 'bg-ok/20 text-ok'
      : action.riskLevel === 'medium'
        ? 'bg-warn/20 text-warn'
        : 'bg-crit/20 text-crit';

  const status = action.approvalStatus;
  const pending = status === 'pending';

  const approve = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.approve(action.id, engineer || 'Engineer');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const reject = async (reason: string) => {
    setError(null);
    setBusy(true);
    try {
      await api.reject(action.id, engineer || 'Engineer', reason);
      setRejectOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (incidentStatus === 'resolved') {
    return (
      <div className="rounded-lg border border-ok/40 bg-ok/10 px-3 py-3 text-sm text-ok">
        Recovered ★ — remediation complete. Lab metrics returned to baseline.
      </div>
    );
  }

  return (
    <div className="space-y-3 border border-[var(--border)] bg-[var(--bg-raised)] p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs leading-relaxed text-slate-200">{action.description}</p>
        <span className={clsx('shrink-0 rounded px-1.5 py-0.5 text-[10px] uppercase', riskColor)}>
          {action.riskLevel}
        </span>
      </div>

      {action.alternatives && action.alternatives.length > 0 && (
        <ul className="list-disc pl-4 text-[11px] text-slate-500">
          {action.alternatives.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}

      {action.plan && <PlanDetails plan={action.plan} warnings={action.guardrailWarnings} />}

      <p className="text-[11px] text-[var(--text-3)]">
        لا يُنفَّذ أي تغيير دون موافقة مهندس. · No change runs without engineer approval.
      </p>

      {needsInvestigation && (
        <p className="text-[11px] text-warn">
          Low confidence. More investigation is needed before acting.
        </p>
      )}

      {pending && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void approve()}
            className="rq-btn-primary flex-1 px-3"
          >
            {busy ? '…' : t('incident.approve')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setRejectOpen(true)}
            className="rq-btn-secondary px-3"
          >
            {t('incident.reject')}
          </button>
        </div>
      )}

      {(status === 'approved' || status === 'executed' || busy) && !action.dryRun && incidentStatus !== 'resolved' && (
        <div className="text-xs text-info">
          {status === 'executed' ? 'Executed ✓ — Recovering…' : 'Executing on R1…'}
        </div>
      )}

      {action.dryRun && (
        <div className="text-xs text-warn">
          Dry run — execution is switched off, your approval was recorded but nothing was changed.
        </div>
      )}
      {status === 'failed' && <div className="text-xs text-crit">Execution failed</div>}
      {error && <div className="text-[11px] text-crit">{error}</div>}

      {rejectOpen && (
        <RejectDialog onCancel={() => setRejectOpen(false)} onConfirm={(r) => void reject(r)} />
      )}
    </div>
  );
}
