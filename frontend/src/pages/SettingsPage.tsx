import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { applyLang, getTheme, setTheme, type Lang, type Theme } from '@/lib/theme';
import clsx from 'clsx';

const KEY = 'rootiq.engineer';

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState('Rayan');
  const [theme, setThemeState] = useState<Theme>(() => getTheme());
  useEffect(() => {
    setName(localStorage.getItem(KEY) || 'Rayan');
  }, []);

  const onTheme = (tMode: Theme) => {
    setTheme(tMode);
    setThemeState(tMode);
  };

  const onLang = (l: Lang) => {
    void i18n.changeLanguage(l);
    applyLang(l);
  };

  return (
    <div className="mx-auto max-w-lg space-y-6 p-6">
      <h1 className="text-lg font-semibold">{t('nav.settings')}</h1>
      <label className="block text-sm">
        <span className="text-[var(--text-2)]">{t('settings.engineer')}</span>
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            localStorage.setItem(KEY, e.target.value);
          }}
          className="mt-1 w-full rounded-[var(--r-md)] border border-noc-line bg-noc-panel px-3 py-2 outline-none focus:border-info"
        />
      </label>

      <section className="space-y-3 rounded-[var(--r-md)] border border-noc-line bg-noc-panel/60 p-4">
        <h2 className="text-sm font-semibold">{t('settings.appearance')}</h2>
        <div className="flex gap-2">
          {(['dark', 'light'] as Theme[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => onTheme(mode)}
              className={clsx(
                'rounded-[var(--r-md)] px-3 py-1.5 text-xs font-semibold',
                theme === mode
                  ? 'bg-[var(--bg-selected)] text-[var(--brand-text)]'
                  : 'border border-noc-line text-[var(--text-2)] hover:bg-[var(--bg-hover)]',
              )}
            >
              {mode === 'dark' ? t('settings.themeDark') : t('settings.themeLight')}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3 rounded-[var(--r-md)] border border-noc-line bg-noc-panel/60 p-4">
        <h2 className="text-sm font-semibold">{t('settings.language')}</h2>
        <div className="flex gap-2">
          {(['ar', 'en'] as Lang[]).map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => onLang(l)}
              className={clsx(
                'rounded-[var(--r-md)] px-3 py-1.5 text-xs font-semibold',
                i18n.language === l
                  ? 'bg-[var(--bg-selected)] text-[var(--brand-text)]'
                  : 'border border-noc-line text-[var(--text-2)] hover:bg-[var(--bg-hover)]',
              )}
            >
              {l === 'ar' ? 'العربية' : 'English'}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
