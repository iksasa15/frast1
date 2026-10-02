import type { Candidate, ScoreKey } from '@/lib/types';

const COLORS: Record<ScoreKey, string> = {
  metric_anomaly: 'var(--crit)',
  dependency_overlap: 'var(--warn)',
  temporal_proximity: 'var(--brand)',
  blast_radius: 'var(--chart-2)',
  historical_support: 'var(--ok)',
};

const WEIGHTS: Record<ScoreKey, number> = {
  metric_anomaly: 0.3,
  dependency_overlap: 0.25,
  temporal_proximity: 0.2,
  blast_radius: 0.15,
  historical_support: 0.1,
};

const KEYS = Object.keys(WEIGHTS) as ScoreKey[];

export function CandidateRanking({ candidates }: { candidates: Candidate[] }) {
  return (
    <div className="space-y-3">
      {candidates.slice(0, 3).map((c, i) => {
        const parts = KEYS.map((k) => ({
          k,
          w: WEIGHTS[k] * (c.components[k] ?? 0),
          color: COLORS[k],
        }));
        const total = parts.reduce((s, p) => s + p.w, 0) || 1;
        return (
          <div key={c.entityId} className="rounded-lg border border-noc-line bg-noc-bg/40 p-2.5">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-semibold">
                #{i + 1} {c.label}
              </span>
              <span className="font-mono text-slate-400">{c.score.toFixed(2)}</span>
            </div>
            <div className="flex h-2 overflow-hidden rounded-full bg-noc-line">
              {parts.map((p) => (
                <div
                  key={p.k}
                  style={{ width: `${(p.w / total) * 100}%`, background: p.color }}
                  title={`${p.k}: ${p.w.toFixed(3)}`}
                />
              ))}
            </div>
            {c.suppressedBy && (
              <p className="mt-1 text-[10px] text-slate-500">
                Symptom — downstream of {c.suppressedBy}
              </p>
            )}
          </div>
        );
      })}
      <div className="flex flex-wrap gap-2 text-[9px] text-slate-500">
        {KEYS.map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className="inline-block size-2 rounded-sm" style={{ background: COLORS[k] }} />
            {k.replaceAll('_', ' ')}
          </span>
        ))}
      </div>
    </div>
  );
}
