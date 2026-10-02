export function ModeBadge({ mode }: { mode: 'live' | 'sim' }) {
  const live = mode === 'live';
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${
        live ? 'bg-ok/20 text-ok' : 'bg-info/20 text-info'
      }`}
    >
      {live ? 'LIVE LAB' : 'SIMULATION'}
    </span>
  );
}
