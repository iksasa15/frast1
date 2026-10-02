import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type RunsResp = {
  runs: Array<{
    scenario: string | null;
    mode: string | null;
    incidentId: string;
    metrics: {
      timeToRootCause?: number | null;
      noiseReduction?: number | null;
      correct?: boolean;
      rawAlerts?: number;
    };
  }>;
  summary: {
    count: number;
    top1Accuracy: number | null;
    avgTimeToRootCause: number | null;
    avgNoiseReduction: number | null;
  };
};

export function AnalyticsPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<RunsResp | null>(null);

  useEffect(() => {
    const load = () => {
      void fetch('/api/runs')
        .then((r) => r.json())
        .then((j: RunsResp) => setData(j))
        .catch(() => setData(null));
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const s = data?.summary;
  const chart = (data?.runs ?? []).map((r, i) => ({
    name: `${r.scenario?.slice(0, 8) ?? 'run'}-${i + 1}`,
    ttr: r.metrics.timeToRootCause ?? 0,
  }));

  const cards = [
    {
      label: t('analytics.top1'),
      value:
        s?.top1Accuracy == null
          ? '—'
          : `${Math.round(s.top1Accuracy * (s.count || 0))}/${s.count || 0}`,
    },
    {
      label: t('analytics.avgTtr'),
      value: s?.avgTimeToRootCause == null ? '—' : `${s.avgTimeToRootCause.toFixed(1)}s`,
    },
    {
      label: t('analytics.avgNoise'),
      value: s?.avgNoiseReduction == null ? '—' : `${(s.avgNoiseReduction * 100).toFixed(1)}%`,
    },
    { label: t('analytics.runs'), value: String(s?.count ?? 0) },
  ];

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <h1 className="text-lg font-semibold tracking-wide">{t('analytics.title')}</h1>
      <div className="grid grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-noc-line bg-noc-panel/80 px-3 py-3">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{c.label}</div>
            <div className="mt-1 font-mono text-2xl tabular-nums">{c.value}</div>
          </div>
        ))}
      </div>

      <div className="h-64 rounded-xl border border-noc-line bg-noc-panel/60 p-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart}>
            <CartesianGrid stroke="#1f2a4d" strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} unit="s" />
            <Tooltip
              contentStyle={{ background: '#111831', border: '1px solid #1f2a4d' }}
              labelStyle={{ color: '#cbd5e1' }}
            />
            <ReferenceLine
              y={60}
              stroke="#eab308"
              strokeDasharray="4 4"
              label={{ value: t('analytics.target'), fill: '#eab308', fontSize: 11 }}
            />
            <Bar dataKey="ttr" fill="#38bdf8" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-auto rounded-xl border border-noc-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-noc-panel text-[11px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2 font-normal">#</th>
              <th className="px-3 py-2 font-normal">Scenario</th>
              <th className="px-3 py-2 font-normal">Mode</th>
              <th className="px-3 py-2 font-normal">TTR</th>
              <th className="px-3 py-2 font-normal">Noise</th>
              <th className="px-3 py-2 font-normal">Correct</th>
            </tr>
          </thead>
          <tbody>
            {(data?.runs ?? []).map((r, i) => (
              <tr key={`${r.incidentId}-${i}`} className="border-t border-noc-line/70">
                <td className="px-3 py-2 font-mono">{i + 1}</td>
                <td className="px-3 py-2">
                  <bdi>{r.scenario}</bdi>
                </td>
                <td className="px-3 py-2">{r.mode}</td>
                <td className="px-3 py-2 font-mono tabular-nums">
                  {r.metrics.timeToRootCause?.toFixed?.(1) ?? '—'}s
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">
                  {r.metrics.noiseReduction != null
                    ? `${(r.metrics.noiseReduction * 100).toFixed(1)}%`
                    : '—'}
                </td>
                <td className="px-3 py-2">{r.metrics.correct ? '✓' : '✗'}</td>
              </tr>
            ))}
            {(data?.runs?.length ?? 0) === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                  No completed live incidents yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
