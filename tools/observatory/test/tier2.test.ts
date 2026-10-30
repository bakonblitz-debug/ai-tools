import Sqlite from 'better-sqlite3';
import { expect, it } from 'vitest';
import { startHeatmap } from '../src/heatmap';
import { computeTiles, type SessionRow, type UsageRow } from '../src/metrics';
import { coverage, filterEvents, hookTop, loadEvents, openOtel, toolDecisions, waterfall } from '../src/otel';
import { parseGitLog } from '../src/overlay';
import { applyFilters, href, parseQuery } from '../src/query';

let n = 0;
const s = (o: Partial<SessionRow> = {}): SessionRow => ({
  session: `s${n++}`, date: '2026-10-08', machine: 'mac', scratch: 0, agent_kind: 'interactive', active_s: 3600, assistant_msgs: 10,
  interruptions: 0, tool_errors: 0, denials: 0, tokens_in: 0, tokens_out: 0, cache_read: 0, cache_create: 0, model: 'opus', project: 'alpha', ...o,
});
const u = (o: Partial<UsageRow> = {}): UsageRow => ({
  session: 's0', date: '2026-10-08', machine: 'mac', scratch: 0, agent: 'main', requests: 1, cost_usd: 0, effort: 'high', ...o,
});

// ---- filters
it('narrows by project, model and effort; "not set" matches empty effort; subagents follow their parent', () => {
  const ss = [s({ session: 'a', project: 'alpha', model: 'opus' }), s({ session: 'b', project: 'beta', model: 'haiku' }), s({ session: 'a/x', project: 'alpha', model: 'haiku' })];
  const uu = [u({ session: 'a', effort: 'high' }), u({ session: 'a/x', effort: '' }), u({ session: 'b', effort: '' })];
  const ids = (f: object) => applyFilters(ss, uu, { project: '', model: '', effort: '', ...f }).sessions.map((r) => r.session);
  expect(ids({ project: 'beta' })).toEqual(['b']);
  expect(ids({ model: 'opus' })).toEqual(['a', 'a/x']);
  expect(ids({ effort: 'not set' })).toEqual(['a', 'b', 'a/x']);
  expect(ids({ effort: 'high', project: 'alpha' })).toEqual(['a', 'a/x']);
  expect(applyFilters(ss, uu, { project: '', model: '', effort: 'not set' }).usage.map((r) => r.session)).toEqual(['a/x', 'b']);
});

it('filtered data narrows the tiles', () => {
  const ss = [s({ session: 'a', project: 'alpha' }), s({ session: 'b', project: 'beta' })];
  const q = parseQuery({ project: 'beta', days: '7' }, '2026-10-10');
  const f = applyFilters(ss, [], q);
  const t = computeTiles(f.sessions, f.usage, { machine: 'all', scratch: false, agent: 'all', days: q.days, today: q.today }, null).find((x) => x.id === 'sessions')!;
  expect(t.n).toBe(1);
});

it('from/to define the window and survive in links; bad dates fall back to days', () => {
  const q = parseQuery({ from: '2026-10-01', to: '2026-10-10' }, '2026-10-30');
  expect([q.days, q.today, q.custom]).toEqual([10, '2026-10-10', true]);
  expect(href(q)).toBe('?from=2026-10-01&to=2026-10-10');
  const bad = parseQuery({ from: 'nope', days: '7' }, '2026-10-30');
  expect([bad.days, bad.today, bad.custom]).toEqual([7, '2026-10-30', false]);
  expect(href(parseQuery({ project: 'a b', overlay: 'plugins' }, '2026-10-30'))).toBe('?project=a+b&overlay=plugins');
});

// ---- git overlay
const H = (c: string) => c.repeat(40);
const LOG = [
  `${H('a')}\t2026-10-30T17:42:44-04:00\tobservatory: receiver in compose`, 'tools/observatory/Makefile', 'plugins/x/hook.json', '',
  `${H('b')}\t2026-10-29T09:00:00-04:00\tdocs`, 'README.md', '',
  `${H('c')}\t2026-10-28T09:00:00-04:00\ttune`, 'CLAUDE.md', 'config/a.toml', 'scripts/run.sh', 'x/settings.local.json', '',
  `${H('d')}\t2026-09-01T09:00:00-04:00\told`, 'CLAUDE.md', '',
].join('\n');

it('tags commits by touched path, defaults to other, and applies the window', () => {
  const c = parseGitLog(LOG, '2026-10-01', '2026-10-30');
  expect(c.map((x) => x.hash[0])).toEqual(['a', 'b', 'c']);
  expect(c[0]!.tags).toEqual(['other', 'plugins']);
  expect(c[1]!.tags).toEqual(['other']);
  expect(c[2]!.tags.sort()).toEqual(['CLAUDE.md', 'scripts', 'settings']);
  expect(c[0]!.subject).toBe('observatory: receiver in compose');
  expect(parseQuery({}, '2026-10-30').overlay).not.toContain('other');
});

// ---- otel fixture
const T = (d: string) => Date.parse(d + 'T15:00:00Z');
function fixture() {
  const db = new Sqlite(':memory:');
  db.exec('create table otel_events (id integer primary key, received_at integer, name text, ts integer, session_id text, prompt_id text, request_id text, machine text, attrs text)');
  const ins = db.prepare('insert into otel_events (received_at,name,ts,session_id,prompt_id,request_id,machine,attrs) values (0,?,?,?,?,?,?,?)');
  return { db, add: (name: string, ts: number, o: { s?: string; p?: string; r?: string; m?: string } = {}, a: object = {}) => ins.run(name, ts, o.s ?? 'S', o.p ?? null, o.r ?? null, o.m ?? 'mac', JSON.stringify(a)) };
}

it('coverage ratio per day and machine, grey under 90%, empty db is not a crash', () => {
  const { db, add } = fixture();
  for (let i = 0; i < 9; i++) add('api_request', T('2026-10-29') + i);
  for (let i = 0; i < 5; i++) add('api_request', T('2026-10-30') + i);
  for (let i = 0; i < 3; i++) add('api_request', T('2026-10-30') + i, { m: 'pc' });
  const evs = loadEvents(db, '2026-10-29', '2026-10-30', 'UTC');
  const ss = [s({ date: '2026-10-29', assistant_msgs: 10 }), s({ date: '2026-10-30', assistant_msgs: 5 }), s({ date: '2026-10-30', machine: 'pc', assistant_msgs: 6 })];
  const c = coverage(evs, ss, ['2026-10-28', '2026-10-29', '2026-10-30']);
  expect(c.rows.find((r) => r.date === '2026-10-29')).toMatchObject({ ratio: 0.9, grey: false });
  expect(c.rows.find((r) => r.date === '2026-10-30' && r.machine === 'pc')).toMatchObject({ ratio: 0.5, grey: true });
  expect(c.grey).toEqual([false, false, true]);
  expect(coverage([], [], ['2026-10-30'])).toEqual({ rows: [], grey: [false], combined: [null] });
  expect(openOtel('/nonexistent/otel.db')).toBeNull();
});

it('filters events by machine, model and effort (non-request events follow their session)', () => {
  const { db, add } = fixture();
  add('api_request', T('2026-10-30'), { s: 'A' }, { model: 'opus', effort: 'high' });
  add('api_request', T('2026-10-30'), { s: 'B', m: 'pc' }, { model: 'haiku' });
  add('tool_result', T('2026-10-30'), { s: 'A' }, {});
  add('tool_result', T('2026-10-30'), { s: 'B', m: 'pc' }, {});
  const evs = loadEvents(db, '2026-10-30', '2026-10-30', 'UTC');
  const names = (f: object) => filterEvents(evs, { machine: 'all', model: '', effort: '', ...f }).map((e) => e.session_id + e.name);
  expect(names({ model: 'opus' })).toEqual(['Aapi_request', 'Atool_result']);
  expect(names({ effort: 'not set' })).toEqual(['Bapi_request', 'Btool_result']);
  expect(names({ machine: 'pc' })).toHaveLength(2);
});

it('hook top list: totals, count, p50/p95', () => {
  const { db, add } = fixture();
  for (let i = 1; i <= 20; i++) add('hook_execution_complete', T('2026-10-30') + i, {}, { hook_event: 'Stop', hook_name: 'aaa', total_duration_ms: String(i * 10) });
  add('hook_execution_complete', T('2026-10-30'), {}, { hook_event: 'SessionStart', hook_name: 'bbb', total_duration_ms: '5000' });
  const top = hookTop(loadEvents(db, '2026-10-30', '2026-10-30', 'UTC'));
  expect(top[0]).toEqual({ event: 'SessionStart', name: 'bbb', count: 1, total_ms: 5000, p50: 5000, p95: 5000 });
  expect(top[1]).toMatchObject({ name: 'aaa', count: 20, total_ms: 2100, p50: 100, p95: 190 });
});

it('tool decisions by source per day', () => {
  const { db, add } = fixture();
  add('tool_decision', T('2026-10-29'), {}, { source: 'config' });
  add('tool_decision', T('2026-10-30'), {}, { source: 'config' });
  add('tool_decision', T('2026-10-30'), {}, { source: 'user_reject' });
  const d = toolDecisions(loadEvents(db, '2026-10-29', '2026-10-30', 'UTC'), ['2026-10-29', '2026-10-30']);
  expect(d.config).toEqual([1, 1]);
  expect(d.user_reject).toEqual([0, 1]);
  expect(d.hook).toEqual([0, 0]);
});

it('waterfall orders requests, attaches tool results and errors, offsets from the first', () => {
  const { db, add } = fixture();
  const t = T('2026-10-30');
  add('api_request', t + 5000, { r: 'r2', p: 'p1' }, { model: 'opus', effort: 'high', duration_ms: 900, input_tokens: 3 });
  add('api_request', t, { r: 'r1', p: 'p1' }, { model: 'opus', duration_ms: 400, ttft_ms: 100, cost_usd: 0.5 });
  add('tool_result', t + 6000, { r: 'r2' }, { tool_name: 'Bash', success: 'true', duration_ms: 20 });
  add('tool_result', t + 1000, { p: 'p1' }, { tool_name: 'Read', success: 'false', duration_ms: 5 }); // no request_id: falls to latest earlier request
  add('api_error', t + 5100, { r: 'r2' }, { status_code: 529 });
  add('api_error', t + 9000, { r: 'zz' }, {});
  const w = waterfall(loadEvents(db, '2026-10-30', '2026-10-30', 'UTC'));
  expect(w.rows.map((r) => [r.offset_ms, r.effort])).toEqual([[0, 'not set'], [5000, 'high']]);
  expect(w.rows[0]).toMatchObject({ duration_ms: 400, ttft_ms: 100, cost: 0.5, tools: [{ tool: 'Read', success: false }] });
  expect(w.rows[1]!.tools.map((x) => x.tool)).toEqual(['Bash']);
  expect(w.rows[1]!.errors).toEqual([{ error: '', status: '529' }]);
  expect(w.orphanErrors).toHaveLength(1);
});

// ---- heatmap
it('buckets session starts by weekday and hour in the given zone', () => {
  // 2026-10-30 is a Friday; 03:30 UTC is Thursday 23:30 in Toronto (UTC-4)
  const g = startHeatmap(['2026-10-30T03:30:00', '2026-10-30T20:00:00', null, 'junk'], 'America/Toronto');
  expect(g[3]![23]).toBe(1);
  expect(g[4]![16]).toBe(1);
  expect(g.flat().reduce((a, b) => a + b, 0)).toBe(2);
  expect(startHeatmap(['2026-10-30T03:30:00'], 'UTC')[4]![3]).toBe(1);
});
