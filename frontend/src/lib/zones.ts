/** Campus zone colors — distinguish buildings / fabric areas on the topology map. */
export type ZoneId = 'edge' | 'core' | 'building-a' | 'building-b' | 'demo' | 'datacenter';

export type ZoneMeta = {
  id: ZoneId;
  label: string;
  labelAr: string;
  /** Accent for device borders / badges */
  color: string;
  /** Translucent panel fill behind devices */
  fill: string;
  /** Soft border for the zone panel */
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
    label: 'Building A',
    labelAr: 'المبنى أ',
    color: '#4ADE80',
    fill: 'rgba(74, 222, 128, 0.08)',
    border: 'rgba(74, 222, 128, 0.35)',
  },
  'building-b': {
    id: 'building-b',
    label: 'Building B',
    labelAr: 'المبنى ب',
    color: '#A78BFA',
    fill: 'rgba(167, 139, 250, 0.08)',
    border: 'rgba(167, 139, 250, 0.35)',
  },
  demo: {
    id: 'demo',
    label: 'Demo Lab',
    labelAr: 'مختبر العرض',
    color: '#FBBF24',
    fill: 'rgba(251, 191, 36, 0.10)',
    border: 'rgba(251, 191, 36, 0.40)',
  },
  datacenter: {
    id: 'datacenter',
    label: 'Data Center',
    labelAr: 'مركز البيانات',
    color: '#FB7185',
    fill: 'rgba(251, 113, 133, 0.08)',
    border: 'rgba(251, 113, 133, 0.35)',
  },
};

export function zoneOf(id: string | undefined | null): ZoneMeta | null {
  if (!id || !(id in ZONES)) return null;
  return ZONES[id as ZoneId];
}
