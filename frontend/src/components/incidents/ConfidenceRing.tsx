import { useEffect, useState } from 'react';
import { cssToken } from '@/lib/theme';

export function ConfidenceRing({ value }: { value: number }) {
  const r = 33;
  const c = 2 * Math.PI * r;
  const pct = Math.round(value * 100);
  const [brand, setBrand] = useState('#3DD6F5');
  const [track, setTrack] = useState('rgba(169, 176, 224, .20)');
  const [fg, setFg] = useState('#E8EBFF');

  useEffect(() => {
    const sync = () => {
      setBrand(cssToken('--brand', '#3DD6F5'));
      setTrack(cssToken('--border', 'rgba(169, 176, 224, .20)'));
      setFg(cssToken('--text-1', '#E8EBFF'));
    };
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, []);

  return (
    <svg width="72" height="72" viewBox="0 0 72 72" role="img" aria-label={`confidence ${pct}%`}>
      <circle cx="36" cy="36" r={r} stroke={track} strokeWidth="6" fill="none" />
      <circle
        cx="36"
        cy="36"
        r={r}
        stroke={brand}
        strokeWidth="6"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - value)}
        transform="rotate(-90 36 36)"
        style={{ transition: 'stroke-dashoffset var(--dur-slow) var(--ease-out)' }}
      />
      <text
        x="36"
        y="40"
        textAnchor="middle"
        fill={fg}
        className="rq-mono"
        style={{ fontSize: 16, fontWeight: 500 }}
      >
        {pct}%
      </text>
    </svg>
  );
}
