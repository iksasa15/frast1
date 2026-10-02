import { useEffect, useState } from 'react';

const KEY = 'rootiq.engineer';

export function SettingsPage() {
  const [name, setName] = useState('Ahmed');

  useEffect(() => {
    setName(localStorage.getItem(KEY) || 'Ahmed');
  }, []);

  return (
    <div className="mx-auto max-w-lg space-y-6 p-6">
      <h1 className="text-lg font-semibold">Settings</h1>
      <label className="block text-sm">
        <span className="text-slate-400">Engineer name (for Approve / Reject)</span>
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            localStorage.setItem(KEY, e.target.value);
          }}
          className="mt-1 w-full rounded-lg border border-noc-line bg-noc-panel px-3 py-2 outline-none focus:border-info"
        />
      </label>
      <p className="rounded-lg border border-noc-line bg-noc-panel/60 p-4 text-xs text-slate-400">
        RootIQ uses the live collector feed only. Discovery health and errors are shown in the top bar.
      </p>
    </div>
  );
}
