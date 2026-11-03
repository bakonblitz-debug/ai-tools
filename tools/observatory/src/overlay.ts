import { execFileSync } from 'node:child_process';
import { tz } from './query';

export type Commit = { hash: string; date: string; at: string; subject: string; tags: string[] };

export const tagOf = (path: string) =>
  /(^|\/)CLAUDE\.md$/.test(path) ? 'CLAUDE.md'
  : /(^|\/)settings[^/]*\.json$/.test(path) || path.startsWith('config/') ? 'settings'
  : path.startsWith('plugins/') ? 'plugins'
  : path.startsWith('scripts/') ? 'scripts' : 'other';

/** Local wall-clock `YYYY-MM-DDTHH:mm` of an instant in `zone`. */
const localAt = (iso: string, zone: string) => {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
};

/** Parses `git log --format=%H%x09%cI%x09%s --name-only`; keeps commits whose local date in `zone` is within [from, to]. */
export function parseGitLog(text: string, from: string, to: string, zone = 'UTC'): Commit[] {
  const out: Commit[] = [];
  let cur: (Commit & { set: Set<string> }) | undefined;
  const done = () => { if (cur) out.push({ hash: cur.hash, date: cur.date, at: cur.at, subject: cur.subject, tags: cur.set.size ? [...cur.set] : ['other'] }); };
  for (const line of text.split(/\r?\n/)) {
    const m = /^([0-9a-f]{40})\t([^\t]+)\t(.*)$/.exec(line);
    if (m) { done(); const at = localAt(m[2]!, zone); cur = { hash: m[1]!, date: at.slice(0, 10), at, subject: m[3]!, tags: [], set: new Set() }; }
    else if (cur && line.trim()) cur.set.add(tagOf(line.trim()));
  }
  done();
  return out.filter((c) => c.date >= from && c.date <= to);
}

/** git reads a bare date with the current time of day, so start two days early; parseGitLog trims to the window. */
export const sinceFor = (from: string) => new Date(Date.parse(from) - 2 * 86400000).toISOString().slice(0, 10);

/** Harness repo history, newest first; empty when the mount or git is missing. */
export function readCommits(from: string, to: string, repo = process.env.HARNESS_DIR ?? '/data/harness'): Commit[] {
  try {
    const text = execFileSync('git', ['-c', `safe.directory=${repo}`, '-C', repo, 'log', `--since=${sinceFor(from)}`, '--format=%H%x09%cI%x09%s', '--name-only'], { encoding: 'utf8', maxBuffer: 32e6, stdio: ['ignore', 'pipe', 'ignore'] });
    return parseGitLog(text, from, to, tz());
  } catch { return []; }
}
