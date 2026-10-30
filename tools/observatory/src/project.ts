type Env = Record<string, string | undefined>;
const list = (s?: string) => (s ?? '').split(',').map((x) => x.trim()).filter(Boolean);

export function normalizeProject(raw: string, env: Env): string {
  for (const p of list(env.WORKSPACE_PREFIXES)) {
    if (raw === p || raw === p + '-') return '(workspace)';
    if (raw.startsWith(p + '-')) return raw.slice(p.length + 1);
  }
  if (list(env.HOME_PREFIXES).includes(raw)) return '~';
  const m = /^\/m(?:\/(.*))?$/.exec(raw);
  if (m) return (m[1] ?? '').replace(/\/+$/, '').replaceAll('/', '-') || '(workspace)';
  return raw;
}

export const isScratch = (raw: string): boolean =>
  ['-private-tmp', '-private-var', '-AppData-Local-Temp-'].some((s) => raw.includes(s)) || raw.endsWith('-WINDOWS-system32');
