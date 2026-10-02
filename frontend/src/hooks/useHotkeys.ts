import { useEffect } from 'react';

export function useHotkeys(onTogglePresenter: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!e.shiftKey || (e.target as HTMLElement).closest('input,textarea')) return;
      const map: Record<string, () => unknown> = {
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
