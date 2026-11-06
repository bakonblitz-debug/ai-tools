import { buildMarks } from '../src/chart';
import { ensureFresh, openDb, readMeta } from '../src/loader';
import type { SessionRow, UsageRow } from '../src/metrics';
import { readCommits } from '../src/overlay';
import { applyFilters, dayList, parseQuery, type RawQ, tz } from '../src/query';

export const METRICS_DIR = process.env.METRICS_DIR_IN_CONTAINER ?? '/data/metrics';
export const TAG_COLORS: Record<string, string> = { 'CLAUDE.md': '#c2185b', settings: '#00838f', plugins: '#6d4c41', scripts: '#7b1fa2', other: '#78909c' };
let db: ReturnType<typeof openDb> | undefined;

const KINDS = { interactive: ['interactive', 'subagent'], headless: ['headless', 'hook'] } as Record<string, string[]>;

/** Everything a page needs from the query string: validated filters, loaded rows, filtered rows, commits for overlays. */
export async function loadCtx(sp: RawQ) {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: tz() });
  const q = parseQuery(sp, today);
  db ??= openDb();
  ensureFresh(db, METRICS_DIR, process.env);
  const meta = readMeta(db);
  const sessions = db.prepare('SELECT * FROM sessions').all() as SessionRow[];
  const usage = db.prepare('SELECT * FROM usage').all() as UsageRow[];
  const dates = dayList(q);
  const f = applyFilters(sessions, usage, q);
  const inScope = (r: { date: string; machine: string; scratch: number }) =>
    dates.includes(r.date) && (q.machine === 'all' || r.machine === q.machine) && (q.scratch || !r.scratch);
  const kinds = KINDS[q.agent];
  // main sessions inside the global filters (what the Sessions table and heatmap list)
  const scoped = f.sessions.filter((r) => !r.session.includes('/') && inScope(r) && (!kinds || kinds.includes(r.agent_kind)));
  const commits = readCommits(dates[0]!, q.today);
  const marks = buildMarks(commits, q.overlay, TAG_COLORS);
  const uniq = (xs: (string | null | undefined)[]) => [...new Set(xs.filter((x): x is string => !!x))].sort();
  return {
    q, db, meta, sessions, usage, f, dates, scoped, commits, marks,
    projects: uniq(sessions.map((r) => r.project)), models: uniq(sessions.map((r) => r.model)),
  };
}
export type Ctx = Awaited<ReturnType<typeof loadCtx>>;
