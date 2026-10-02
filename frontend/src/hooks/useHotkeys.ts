import { useEffect } from 'react';
import { api } from '@/lib/api';

export function useHotkeys(onTogglePresenter: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!e.shiftKey || (e.target as HTMLElement).closest('input,textarea')) return;
      const map: Record<string, () => unknown> = {
        Digit1: () => api.inject('uplink-congestion'),
        Digit2: () => api.inject('dns-failure'),
        Digit3: () => api.inject('server-spike'),
        KeyR: () => api.reset(),
        KeyP: onTogglePresenter,
      };
      if (map[e.code]) {
        e.preventDefault();
        Promise.resolve(map[e.code]()).catch(console.error);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onTogglePresenter]);
}
