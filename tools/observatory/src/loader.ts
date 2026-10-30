import Sqlite, { type Database } from 'better-sqlite3';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { isScratch, normalizeProject } from './project';

type Env = Record<string, string | undefined>;
type Row = Record<string, string | number | null>;

const SESSION_NUM = 'duration_s active_s assistant_msgs interruptions tool_errors denials generated_edits tokens_in tokens_out cache_read cache_create thinking result_bytes context_read_bytes code_read_bytes'.split(' ');
const SESSION_TXT = ['session', 'date', 'started', 'ended', 'models'];
const USAGE_NUM = ['requests', 'output', 'thinking', 'cost_usd'];
const USAGE_TXT = ['session', 'date', 'agent', 'activity'];
const MACHINES = [['mac', ''], ['pc', 'pc/']] as const;
const FILES = MACHINES.flatMap(([, d]) => [d + 'sessions.tsv', d + 'usage.tsv']);

const cols = (txt: string[], num: string[]) =>
  [...txt.map((c) => `${c} TEXT`), ...num.map((c) => `${c} REAL`)].join(', ');

function migrate(db: Database) {
  // older schema without agent_kind: drop so the next load rebuilds it
  if (db.prepare("SELECT 1 FROM pragma_table_info('sessions')").get() && !db.prepare("SELECT 1 FROM pragma_table_info('sessions') WHERE name='agent_kind'").get()) db.exec('DROP TABLE sessions; DROP TABLE IF EXISTS load_meta');
  db.pragma('busy_timeout = 5000');
  db.exec(`
CREATE TABLE IF NOT EXISTS sessions (${cols(SESSION_TXT, SESSION_NUM)}, machine TEXT, project_raw TEXT, project TEXT, scratch INTEGER, model TEXT, agent_kind TEXT);
CREATE TABLE IF NOT EXISTS usage (${cols(USAGE_TXT, USAGE_NUM)}, effort TEXT, machine TEXT, project_raw TEXT, project TEXT, scratch INTEGER);
CREATE TABLE IF NOT EXISTS load_meta (json TEXT);`);
}

/** Header = last "# " line; rows mapped by name; short rows keep nulls and count as ragged. */
function parse(path: string) {
  if (!existsSync(path)) return { rows: [] as Row[], ragged: 0, preEffort: 0, text: '' };
  const text = readFileSync(path, 'utf8');
  const lines = text.split(/\r?\n/);
  const h = lines.filter((l) => l.startsWith('# ')).pop();
  const header = h ? h.slice(2).split('\t') : [];
  const rows: Row[] = [];
  let ragged = 0, preEffort = 0;
  for (const l of lines) {
    if (!l.trim() || l.startsWith('#')) continue;
    const f = l.split('\t');
    if (f[0] === header[0]) continue;
    // a usage row missing only the trailing effort column is a known schema step, not damage
    if (f.length < header.length) (f.length === header.length - 1 && header.at(-1) === 'effort' ? preEffort++ : ragged++);
    rows.push(Object.fromEntries(header.map((k, i) => [k, f[i] ?? null])));
  }
  return { rows, ragged, preEffort, text };
}

const num = (v: unknown) => (v == null || v === '' ? null : Number(v));

function sessionModel(models: unknown) {
  const real = String(models ?? '').split(',').map((m) => m.trim()).filter((m) => m && m !== '<synthetic>');
  return real.length === 0 ? null : real.length === 1 ? real[0]! : 'mixed';
}

const mtimes = (dir: string) =>
  Object.fromEntries(FILES.map((f) => [f, existsSync(join(dir, f)) ? statSync(join(dir, f)).mtimeMs : 0]));

export function load(db: Database, dir: string, env: Env): void {
  migrate(db);
  const now = new Date().toISOString();
  const refused: string[] = [];
  const rowsMeta: Record<string, number> = {};
  const ragged: Record<string, number> = { mac: 0, pc: 0 };
  const preEffort: Record<string, number> = { mac: 0, pc: 0 };
  let pricesAsOf: string | null = null;

  db.transaction(() => {
    for (const [machine, sub] of MACHINES) {
      for (const table of ['sessions', 'usage'] as const) {
        const file = `${sub}${table}.tsv`;
        const p = parse(join(dir, file));
        ragged[machine]! += p.ragged;
        preEffort[machine]! += p.preEffort;
        rowsMeta[`${table}.${machine}`] = p.rows.length;
        if (table === 'usage') pricesAsOf ??= /PRICES as of (\d{4}-\d{2}-\d{2})/.exec(p.text)?.[1] ?? null;
        const prev = (db.prepare(`SELECT count(*) c FROM ${table} WHERE machine=?`).get(machine) as { c: number }).c;
        if (p.rows.length < prev) {
          refused.push(`${file}: ${prev} → ${p.rows.length} rows, kept previous`);
          rowsMeta[`${table}.${machine}`] = prev;
          continue;
        }
        db.prepare(`DELETE FROM ${table} WHERE machine=?`).run(machine);
        const txt = table === 'sessions' ? SESSION_TXT : USAGE_TXT;
        const nums = table === 'sessions' ? SESSION_NUM : USAGE_NUM;
        const extra = table === 'sessions' ? ['model'] : ['effort'];
        const names = [...txt, ...nums, ...extra, 'machine', 'project_raw', 'project', 'scratch'];
        const ins = db.prepare(`INSERT INTO ${table} (${names.join(',')}) VALUES (${names.map(() => '?').join(',')})`);
        for (const r of p.rows) {
          const raw = String(r.project ?? '');
          ins.run(
            ...txt.map((c) => r[c] ?? null),
            ...nums.map((c) => num(r[c])),
            table === 'sessions' ? sessionModel(r.models) : (r.effort ?? ''),
            machine, raw, normalizeProject(raw, env), isScratch(raw) ? 1 : 0,
          );
        }
      }
    }
    db.exec(AGENT_KIND_SQL);
    const meta = { loadedAt: now, mtimes: mtimes(dir), rows: rowsMeta, ragged, preEffort, pricesAsOf, refused: refused.length ? refused.join('; ') : null };
    db.prepare('DELETE FROM load_meta').run();
    db.prepare('INSERT INTO load_meta (json) VALUES (?)').run(JSON.stringify(meta));
  })();
}

/** Reloads only when a file's mtime differs from the last load. Returns whether it reloaded. */
export function ensureFresh(db: Database, dir: string, env: Env): boolean {
  migrate(db);
  const row = db.prepare('SELECT json FROM load_meta').get() as { json: string } | undefined;
  const last = row ? JSON.parse(row.json).mtimes : null;
  if (last && JSON.stringify(last) === JSON.stringify(mtimes(dir))) return false;
  load(db, dir, env);
  return true;
}

export function readMeta(db: Database) {
  const row = db.prepare('SELECT json FROM load_meta').get() as { json: string } | undefined;
  return row ? JSON.parse(row.json) : null;
}

export function openDb(path = process.env.DB_PATH ?? '/data/db/observatory.db'): Database {
  const db = new Sqlite(path);
  db.pragma('journal_mode = WAL');
  db.pragma('busy_timeout = 5000');
  return db;
}

// A session's kind comes from the agent of its own (exact-id) usage rows; subagent rows carry "/" in the id.
// No real model (only <synthetic>) = it never made an API request, e.g. a run that was not logged in.
const AGENT_KIND_SQL = `UPDATE sessions SET agent_kind = CASE WHEN instr(session, '/') > 0 THEN 'subagent'
  WHEN model IS NULL THEN 'no-api' ELSE COALESCE((
  SELECT CASE WHEN u.agent = 'main' THEN 'interactive' WHEN u.agent = 'headless' THEN 'headless' WHEN u.agent LIKE 'hook:%' THEN 'hook' END
  FROM usage u WHERE u.session = sessions.session AND u.machine = sessions.machine LIMIT 1), 'unknown') END`;
