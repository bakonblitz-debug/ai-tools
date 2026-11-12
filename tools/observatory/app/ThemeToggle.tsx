'use client';
import { useEffect, useState } from 'react';

type Mode = 'system' | 'light' | 'dark';
const NEXT: Record<Mode, Mode> = { system: 'dark', dark: 'light', light: 'system' };
const LABEL: Record<Mode, string> = { system: '◐ System', dark: '☾ Dark', light: '☀ Light' };

/** Theme switch, top right: system → dark → light. Pinned choice kept per browser; system follows the OS. */
export default function ThemeToggle() {
  const [mode, setMode] = useState<Mode>('system');
  useEffect(() => {
    const t = document.documentElement.dataset.theme;
    setMode(t === 'light' || t === 'dark' ? t : 'system');
  }, []);
  const next = () => {
    const m = NEXT[mode];
    setMode(m);
    if (m === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = m;
    try { if (m === 'system') localStorage.removeItem('obs-theme'); else localStorage.setItem('obs-theme', m); } catch { /* storage blocked: the choice lasts this page only */ }
  };
  return (
    <button type="button" onClick={next} aria-label={`Theme: ${mode}. Switch to ${NEXT[mode]}`}
      className="fixed right-3 top-3 z-20 rounded-full border border-outline bg-surface px-3 py-1 text-xs text-on-surface-variant shadow-e1 hover:text-on-surface">
      {LABEL[mode]}
    </button>
  );
}
