import { execFileSync } from 'node:child_process';

export type Commit = { hash: string; date: string; subject: string; tags: string[] };

export const tagOf = (path: string) =>
  /(^|\/)CLAUDE\.md$/.test(path) ? 'CLAUDE.md'
  : /(^|\/)settings[^/]*\.json$/.test(path) || path.startsWith('config/') ? 'settings'
  : path.startsWith('plugins/') ? 'plugins'
  : path.startsWith('scripts/') ? 'scripts' : 'other';

/** Parses `git log --format=%H%x09%cI%x09%s --name-only`; keeps commits dated within [from, to]. */
export function parseGitLog(text: string, from: string, to: string): Commit[] {
  const out: Commit[] = [];
  let cur: (Commit & { set: Set<string> }) | undefined;
  const done = () => { if (cur) out.push({ hash: cur.hash, date: cur.date, subject: cur.subject, tags: cur.set.size ? [...cur.set] : ['other'] }); };
  for (const line of text.split(/\r?\n/)) {
    const m = /^([0-9a-f]{40})\t(\d{4}-\d{2}-\d{2})[^\t]*\t(.*)$/.exec(line);
    if (m) { done(); cur = { hash: m[1]!, date: m[2]!, subject: m[3]!, tags: [], set: new Set() }; }
    else if (cur && line.trim()) cur.set.add(tagOf(line.trim()));
  }
  done();
  return out.filter((c) => c.date >= from && c.date <= to);
}

/** Harness repo history, newest first; empty when the mount or git is missing. */
export function readCommits(from: string, to: string, repo = process.env.HARNESS_DIR ?? '/data/harness'): Commit[] {
  try {
    const text = execFileSync('git', ['-c', `safe.directory=${repo}`, '-C', repo, 'log', `--since=${from}`, '--format=%H%x09%cI%x09%s', '--name-only'], { encoding: 'utf8', maxBuffer: 32e6, stdio: ['ignore', 'pipe', 'ignore'] });
    return parseGitLog(text, from, to);
  } catch { return []; }
}
