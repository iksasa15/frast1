import type { Health } from './types';
import { cssToken } from './theme';

/** Topology / SVG status colors — read live tokens so light/dark stay in sync. */
export function statusColor(h: Health): string {
  switch (h) {
    case 'healthy':
      return cssToken('--ok', '#4ADE80');
    case 'warning':
      return cssToken('--warn', '#FFB020');
    case 'degraded':
      return cssToken('--warn', '#FFB020');
    case 'critical':
      return cssToken('--crit', '#FF5C7A');
    default:
      return cssToken('--text-3', '#8E97D4');
  }
}

/** @deprecated Prefer statusColor() — kept as Record for callers that need a static map snapshot. */
export const STATUS_COLOR: Record<Health, string> = {
  healthy: '#4ADE80',
  warning: '#FFB020',
  degraded: '#FFB020',
  critical: '#FF5C7A',
  unknown: '#8E97D4',
};

export const CAUSE_COLOR = '#FF5C7A';
export const IMPACT_COLOR = '#FFB020';
export const BACKUP_COLOR = '#3DD6F5';
