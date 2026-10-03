/** Campus zone colors — buildings / fabric areas on the topology map. */
export type ZoneId = 'edge' | 'core' | 'building-a' | 'building-b' | 'datacenter';

export type ZoneMeta = {
  id: ZoneId;
  label: string;
  labelAr: string;
  color: string;
  fill: string;
  border: string;
};

export const ZONES: Record<ZoneId, ZoneMeta> = {
  edge: {
    id: 'edge',
    label: 'Edge / DMZ',
    labelAr: 'الحافة / DMZ',
    color: '#2DD4BF',
    fill: 'rgba(45, 212, 191, 0.08)',
    border: 'rgba(45, 212, 191, 0.35)',
  },
  core: {
    id: 'core',
    label: 'Core Network',
    labelAr: 'النواة',
    color: '#60A5FA',
    fill: 'rgba(96, 165, 250, 0.08)',
    border: 'rgba(96, 165, 250, 0.35)',
  },
  'building-a': {
    id: 'building-a',
    label: 'Building 1 — Apps',
    labelAr: 'المبنى 1 — التطبيقات',
    color: '#4ADE80',
    fill: 'rgba(74, 222, 128, 0.08)',
    border: 'rgba(74, 222, 128, 0.35)',
  },
  'building-b': {
    id: 'building-b',
    label: 'Building 2 — Data',
    labelAr: 'المبنى 2 — البيانات',
    color: '#A78BFA',
    fill: 'rgba(167, 139, 250, 0.08)',
    border: 'rgba(167, 139, 250, 0.35)',
  },
  datacenter: {
    id: 'datacenter',
    label: 'Building 3 — Compute',
    labelAr: 'المبنى 3 — الحوسبة',
    color: '#FB7185',
    fill: 'rgba(251, 113, 133, 0.08)',
    border: 'rgba(251, 113, 133, 0.35)',
  },
};

export function zoneOf(id: string | undefined | null): ZoneMeta | null {
  if (!id || !(id in ZONES)) return null;
  return ZONES[id as ZoneId];
}

export function zoneBadge(id: ZoneId): string {
  switch (id) {
    case 'building-a':
      return 'B1';
    case 'building-b':
      return 'B2';
    case 'datacenter':
      return 'B3';
    case 'edge':
      return 'EDGE';
    case 'core':
      return 'CORE';
  }
}
