export type Theme = 'dark' | 'light';
export type Lang = 'ar' | 'en';

const THEME_KEY = 'rootiq.theme';

export function getTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === 'light' || stored === 'dark' ? stored : 'dark';
}

export function setTheme(t: Theme) {
  localStorage.setItem(THEME_KEY, t);
  document.documentElement.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', t === 'light' ? '#F3F5FD' : '#0C1030');
}

export function applyLang(l: Lang) {
  document.documentElement.lang = l;
  document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr';
}

export function initAppearance(lang?: Lang) {
  setTheme(getTheme());
  const l =
    lang ??
    ((localStorage.getItem('rootiq.lang') as Lang | null) ||
      (document.documentElement.lang as Lang) ||
      'ar');
  applyLang(l === 'en' ? 'en' : 'ar');
}

/** Read a CSS custom property from :root (for canvas / SVG that need concrete colors). */
export function cssToken(name: string, fallback = ''): string {
  if (typeof document === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
