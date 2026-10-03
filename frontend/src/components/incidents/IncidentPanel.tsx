import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { Incident, IncidentStatus } from '@/lib/types';
import clsx from 'clsx';
import { ConfidenceRing } from './ConfidenceRing';
import { CandidateRanking } from './CandidateRanking';
import { EvidenceList } from './EvidenceList';
import { AffectedServices } from './AffectedServices';
import { ActionCard } from './ActionCard';
import { IncidentReplay } from './IncidentReplay';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';

const STEPS: IncidentStatus[] = [
  'open',
  'investigating',
  'recommendation_ready',
  'awaiting_approval',
  'approved',
  'resolved',
];

interface Props {
  incident: Incident | null;
  onClose?: () => void;
}

export function IncidentPanel({ incident, onClose }: Props) {
  const { t, i18n } = useTranslation();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const elapsed = useMemo(() => {
    if (!incident) return '00:00';
    const ms = now - new Date(incident.openedAt).getTime();
    const s = Math.max(0, Math.floor(ms / 1000));
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }, [incident, now]);

  const conf = incident?.rootCause?.confidence ?? 0;

  if (!incident) {
    return null;
  }

  return (
    <AnimatePresence>
      {incident && (
        <div
          className="absolute end-0 top-0 z-20 h-full"
          style={{ width: 'var(--incident-w)' }}
        >
          <motion.aside
            initial={{ x: 24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 24, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="rq-panel rq-panel--crit flex h-full flex-col bg-noc-panel"
          >
          <header className="border-b border-noc-line px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <div className="rq-mono text-sm text-[var(--brand-text)]">{incident.id}</div>
              <div className="flex items-center gap-2">
                <span
                  data-testid="incident-status"
                  className="rq-mono text-[10px] text-[var(--text-3)]"
                >
                  {incident.status.replaceAll('_', ' ')}
                </span>
                <span
                  className={clsx(
                    'border px-1.5 py-0.5 text-[10px]',
                    incident.severity === 'critical' || incident.severity === 'high'
                      ? 'border-[var(--crit)] text-[var(--crit)]'
                      : 'border-[var(--warn)] text-[var(--warn)]',
                  )}
                >
                  {incident.severity}
                </span>
                <span className="rq-mono text-base tabular-nums">{elapsed}</span>
                {onClose && (
                  <button type="button" onClick={onClose} className="text-[var(--text-3)] hover:text-[var(--text-1)]">
                    ✕
                  </button>
                )}
              </div>
            </div>
            <h2 className="mt-2 text-[15px] font-semibold leading-snug">{incident.title}</h2>
          </header>

          <div className="flex gap-1 border-b border-noc-line px-3 py-3">
            {STEPS.map((step) => {
              const idx = STEPS.indexOf(step);
              const cur = STEPS.indexOf(
                incident.status === 'rejected' ? 'awaiting_approval' : incident.status,
              );
              return (
                <div
                  key={step}
                  title={step.replaceAll('_', ' ')}
                  className={clsx(
                    'rq-stage',
                    idx < cur && 'is-done',
                    idx === cur && 'is-current',
                  )}
                />
              );
            })}
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-4 text-sm">
            {incident.rootCause ? (
              <section className="flex items-start gap-3">
                <ConfidenceRing value={conf} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs uppercase tracking-wider text-slate-500">
                    {t('incident.rootCause')} ·{" "}
                    {incident.rootCause.entityId.startsWith("link-")
                      ? "Network"
                      : incident.rootCause.entityId === "svc-dns"
                        ? "DNS"
                        : "Server"}
                  </div>
                  <div
                    data-testid="root-cause"
                    className="font-semibold text-crit"
                  >
                    {incident.rootCause.label}
                  </div>
                  <div className="font-mono text-[11px] text-slate-400">
                    <bdi>{incident.rootCause.entityId}</bdi>
                  </div>
                  {incident.needsInvestigation && (
                    <div className="mt-2 rounded border border-warn/40 bg-warn/10 px-2 py-1 text-[11px] text-warn">
                      Low confidence — more investigation required
                    </div>
                  )}
                </div>
              </section>
            ) : (
              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Root cause</h3>
                <p className="text-slate-500">Analyzing…</p>
              </section>
            )}

            {incident.candidates?.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                  Why this cause?
                </h3>
                <CandidateRanking candidates={incident.candidates} />
              </section>
            )}

            {incident.explanation && (
              <section>
                <h3 className="mb-1 text-xs uppercase tracking-wider text-slate-500">
                  Explanation{' '}
                  <span className="normal-case text-slate-500">
                    ·{' '}
                    {incident.explanation.source === 'llm'
                      ? 'LLM · grounded ✓'
                      : 'template'}
                  </span>
                </h3>
                <p className="text-xs leading-relaxed text-slate-300">
                  {i18n.language === 'ar' && incident.explanation.ar
                    ? incident.explanation.ar
                    : incident.explanation.en}
                </p>
              </section>
            )}

            <IncidentReplay incidentId={incident.id} />

            <section>
              <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                {t('incident.evidence')}
              </h3>
              <EvidenceList
                evidence={incident.evidence}
                firstAnomalyAt={incident.timings.firstAnomalyAt}
              />
            </section>

            <section>
              <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                Affected services
              </h3>
              <AffectedServices services={incident.affectedServices} />
            </section>

            <section>
              <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                {t('incident.action')}
              </h3>
              {incident.action ? (
                <ActionCard
                  action={incident.action}
                  engineer={
                    typeof window !== 'undefined'
                      ? localStorage.getItem('rootiq.engineer') || 'Ahmed'
                      : 'Ahmed'
                  }
                  incidentStatus={incident.status}
                  needsInvestigation={incident.needsInvestigation}
                />
              ) : (
                <p className="text-slate-500">Waiting for recommendation…</p>
              )}
            </section>

            {incident.verification && incident.verification.total > 0 && (
              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Recovery verification</h3>
                <div
                  className={clsx(
                    'rounded-lg border px-3 py-2 text-xs',
                    incident.verification.status === 'verified'
                      ? 'border-ok/40 bg-ok/10 text-ok'
                      : 'border-warn/40 bg-warn/10 text-warn',
                  )}
                >
                  <div className="mb-1 font-semibold uppercase">
                    {incident.verification.status} · {incident.verification.passed}/{incident.verification.total}
                  </div>
                  <ul className="space-y-0.5 font-mono text-[11px]">
                    {incident.verification.checks.map((c) => (
                      <li key={`${c.entity}-${c.metric}`}>
                        {c.ok ? '✓' : '✗'} {c.metric} {c.op} {c.target} (now {c.observed ?? 'n/a'})
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            )}

            {incident.knowledge && incident.knowledge.similar.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Similar past incidents</h3>
                <ul className="space-y-1 text-xs text-slate-300">
                  {incident.knowledge.similar.map((h) => (
                    <li key={h.id} className="rounded border border-noc-line/70 bg-noc-bg/40 px-2 py-1.5">
                      <div className="font-mono text-[11px] text-info">{h.title}</div>
                      <div className="text-[11px] text-slate-400">{h.snippet}</div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {(incident.knowledge?.aiReference || incident.vendorContext?.aiReference) && (
              <section data-testid="ai-reference">
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">AI reference</h3>
                <div className="space-y-2">
                  {incident.knowledge?.aiReference && (
                    <div className="rounded border border-info/30 bg-info/5 px-2.5 py-2 text-xs text-slate-300">
                      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-info">
                        knowledge · {incident.knowledge.aiReference.gap}
                      </div>
                      <p className="leading-relaxed">{incident.knowledge.aiReference.text}</p>
                    </div>
                  )}
                  {incident.vendorContext?.aiReference && (
                    <div className="rounded border border-info/30 bg-info/5 px-2.5 py-2 text-xs text-slate-300">
                      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-info">
                        vendor · {incident.vendorContext.aiReference.gap}
                      </div>
                      <p className="leading-relaxed">{incident.vendorContext.aiReference.text}</p>
                    </div>
                  )}
                </div>
              </section>
            )}

            <div className="flex items-center justify-between text-[11px] text-slate-500">
              {incident.acknowledgedBy ? (
                <span>Acknowledged by {incident.acknowledgedBy}</span>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    void api.acknowledge(incident.id, localStorage.getItem('rootiq.engineer') || 'Ahmed').catch(() => undefined)
                  }
                  className="rounded border border-noc-line px-2 py-1 text-slate-300 hover:bg-white/5"
                >
                  Acknowledge
                </button>
              )}
            </div>

            <div className="rounded-lg border border-ok/30 bg-ok/10 px-3 py-2 text-xs text-ok">
              Noise reduction:{' '}
              <span className="font-mono text-base">
                {incident.rawAlertCount > 0
                  ? `${Math.min(99, Math.round((1 - 1 / Math.max(incident.rawAlertCount, 1)) * 100))}%`
                  : '—'}
              </span>{' '}
              ({incident.rawAlertCount} alerts → 1 incident)
            </div>
          </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}
