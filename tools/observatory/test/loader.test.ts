import Database from 'better-sqlite3';
import { cpSync, mkdtempSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, it } from 'vitest';
import { ensureFresh, load } from '../src/loader';

const env = { WORKSPACE_PREFIXES: '-Users-alice-www,M-', HOME_PREFIXES: '-Users-alice,C--Users-alice' };
const fx = join(__dirname, 'fixtures');
const count = (db: Database.Database, t: string, m: string) =>
  (db.prepare(`SELECT count(*) c FROM ${t} WHERE machine=?`).get(m) as { c: number }).c;
const meta = (db: Database.Database) => JSON.parse((db.prepare('SELECT json FROM load_meta').get() as { json: string }).json);
const tmp = () => {
  const dir = mkdtempSync(join(tmpdir(), 'obs-'));
  cpSync(fx, dir, { recursive: true });
  return dir;
};

it('loads rows per machine, skips header copies, keeps ragged rows', () => {
  const db = new Database(':memory:');
  load(db, fx, env);
  expect(count(db, 'sessions', 'mac')).toBe(5);
  expect(count(db, 'sessions', 'pc')).toBe(1);
  expect(count(db, 'usage', 'mac')).toBe(4);
  expect(count(db, 'usage', 'pc')).toBe(1);
  const m = meta(db);
  expect(m.ragged.mac).toBe(1); // the short sessions row only
  expect(m.preEffort.mac).toBe(1);
  expect(m.pricesAsOf).toBe('2026-10-28');
  expect(m.refused).toBeNull();
  const r = db.prepare("SELECT * FROM sessions WHERE session='s-ragged'").get() as Record<string, unknown>;
  expect(r.code_read_bytes).toBeNull();
  expect(r.tokens_out).toBe(20);
});

it('derives project, scratch and model', () => {
  const db = new Database(':memory:');
  load(db, fx, env);
  const get = (s: string) => db.prepare('SELECT model, project, scratch FROM sessions WHERE session=?').get(s) as Record<string, unknown>;
  expect(get('s-single')).toEqual({ model: 'claude-opus-5-5', project: 'projects-epicerie', scratch: 0 });
  expect(get('s-mixed').model).toBe('mixed');
  expect(get('s-syn')).toMatchObject({ model: null, scratch: 1 });
  expect(db.prepare("SELECT project FROM sessions WHERE machine='pc'").get()).toEqual({ project: 'projects-epicerie' });
});

it('missing pc dir gives zero pc rows', () => {
  const dir = tmp();
  rmSync(join(dir, 'pc'), { recursive: true });
  const db = new Database(':memory:');
  load(db, dir, env);
  expect(count(db, 'sessions', 'pc')).toBe(0);
  expect(count(db, 'sessions', 'mac')).toBe(5);
  rmSync(dir, { recursive: true });
});

it('refuses a shrinking file and keeps old rows', () => {
  const dir = tmp();
  const db = new Database(':memory:');
  load(db, dir, env);
  writeFileSync(join(dir, 'sessions.tsv'), '# session\tdate\n');
  load(db, dir, env);
  expect(count(db, 'sessions', 'mac')).toBe(5);
  expect(meta(db).refused).toContain('sessions.tsv: 5 → 0 rows, kept previous');
  rmSync(dir, { recursive: true });
});

it('ensureFresh reloads only when an mtime changes', () => {
  const dir = tmp();
  const db = new Database(':memory:');
  expect(ensureFresh(db, dir, env)).toBe(true);
  expect(ensureFresh(db, dir, env)).toBe(false);
  const t = new Date(Date.now() + 5000);
  utimesSync(join(dir, 'usage.tsv'), t, t);
  expect(ensureFresh(db, dir, env)).toBe(true);
  rmSync(dir, { recursive: true });
});

it('derives agent_kind from the usage rows of the main session', () => {
  const db = new Database(':memory:');
  load(db, fx, env);
  const kind = (s: string) => (db.prepare('SELECT agent_kind k FROM sessions WHERE session=?').get(s) as { k: string }).k;
  expect(kind('s-single')).toBe('interactive');
  expect(kind('s-single/ag1')).toBe('subagent');
  expect(kind('s-mixed')).toBe('headless');
  expect(kind('s-syn')).toBe('no-api'); // only <synthetic>: never made a real request
});
