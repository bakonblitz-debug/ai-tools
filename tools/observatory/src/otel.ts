import Sqlite, { type Database } from 'better-sqlite3';
import { existsSync } from 'node:fs';
import type { SessionRow } from './metrics';
import { NOT_SET } from './query';

export type Ev = { name: string; ts: number; date: string; session_id: string | null; prompt_id: string | null; request_id: string | null; machine: string | null; attrs: Record<string, any> };
type DbRow = { name: string; ts: number; session_id: string | null; prompt_id: string | null; request_id: string | null; machine: string | null; attrs: string };

export const GREY_BELOW = 0.9;
const DAY = 86400000;
const API = ['api_request', 'api_error', 'api_refusal'];
export const SOURCES = ['config', 'hook', 'user_permanent', 'user_temporary', 'user_reject', 'user_abort'];

/** Telemetry DB opened read-only in its own connection; null when the receiver has not created it yet. */
export function openOtel(path = process.env.OTEL_DB_PATH ?? '/data/db/otel.db'): Database | null {
  if (!existsSync(path)) return null;
  try { return new Sqlite(path, { readonly: true, fileMustExist: true }); } catch { return null; }
}

export const dateOf = (ms: number, tz?: string) => new Date(ms).toLocaleDateString('en-CA', { timeZone: tz });
const toEv = (r: DbRow, tz?: string): Ev => {
  let attrs: Record<string, any> = {};
  try { attrs = JSON.parse(r.attrs) ?? {}; } catch { /* keep empty */ }
  return { ...r, name: r.name.replace(/^claude_code\./, ''), date: dateOf(r.ts, tz), attrs };
};
const COLS = 'name, ts, session_id, prompt_id, request_id, machine, attrs';

/** Events whose local date falls in [from, to]. */
export function loadEvents(db: Database, from: string, to: string, tz?: string): Ev[] {
  const rows = db.prepare(`SELECT ${COLS} FROM otel_events WHERE ts BETWEEN ? AND ? ORDER BY ts`).all(Date.parse(from) - DAY, Date.parse(to) + 2 * DAY) as DbRow[];
  return rows.map((r) => toEv(r, tz)).filter((e) => e.date >= from && e.date <= to);
}
export function loadSessionEvents(db: Database, id: string, tz?: string): Ev[] {
  return (db.prepare(`SELECT ${COLS} FROM otel_events WHERE session_id = ? ORDER BY ts`).all(id) as DbRow[]).map((r) => toEv(r, tz));
}

/** machine / model / effort. Request events carry model and effort; other events follow their session. */
export function filterEvents(evs: Ev[], f: { machine: string; model: string; effort: string }): Ev[] {
  const m = evs.filter((e) => f.machine === 'all' || e.machine === f.machine);
  if (!f.model && !f.effort) return m;
  const hit = (e: Ev) => (!f.model || e.attrs.model === f.model) && (!f.effort || (e.attrs.effort || NOT_SET) === f.effort);
  const sessions = new Set(m.filter((e) => e.name === 'api_request' && hit(e)).map((e) => e.session_id));
  return m.filter((e) => (API.includes(e.name) ? hit(e) : sessions.has(e.session_id)));
}

export type CoverageRow = { date: string; machine: string; otel: number; transcript: number; ratio: number | null; grey: boolean };
/** Requests that land in a transcript; every other query_source is a side call. */
export const IN_TRANSCRIPT = (qs: unknown) => qs == null || qs === 'repl_main_thread' || qs === 'sdk' || (typeof qs === 'string' && qs.startsWith('agent:'));

/** api_request events with ts in [fromMs, toMs]. */
export function loadRequests(db: Database, fromMs: number, toMs: number, tz?: string): Ev[] {
  return (db.prepare(`SELECT ${COLS} FROM otel_events WHERE name LIKE '%api_request' AND ts BETWEEN ? AND ? ORDER BY ts`).all(fromMs, toMs) as DbRow[]).map((r) => toEv(r, tz));
}

export type CovSession = Pick<SessionRow, 'session' | 'date' | 'machine' | 'assistant_msgs' | 'scratch' | 'started' | 'ended'>;
const baseId = (s: string) => s.split('/')[0]!;
/** Non-scratch main rows dated in `dates` on the machine ('all' = any), plus the subagent rows of those mains. */
export function coverageScope<S extends CovSession>(sessions: S[], dates: string[], machine: string): S[] {
  const mains = new Set(sessions.filter((s) => !s.session.includes('/') && !s.scratch && dates.includes(s.date) && (machine === 'all' || s.machine === machine)).map((s) => s.session));
  return sessions.filter((s) => mains.has(baseId(s.session)));
}

/** api_request events / transcript requests per day and machine; a session family (main row + its `<main>/<agent>` rows) counts on the main row's date and machine; grey = a machine under 90%, never on `today`. */
export function coverage(evs: Ev[], sessions: CovSession[], dates: string[], today?: string) {
  const key = (d: string, m: string) => d + '|' + m;
  const end = (s: CovSession) => (s.ended ? Date.parse(s.ended + 'Z') : 0);
  const day = new Map<string, { date: string; machine: string; endMs: number }>();
  for (const s of sessions) if (!s.session.includes('/')) day.set(s.session, { date: s.date, machine: s.machine, endMs: end(s) });
  const otel = new Map<string, number>(), tr = new Map<string, number>();
  for (const s of sessions) {
    const f = day.get(baseId(s.session));
    if (!f) continue;
    f.endMs = Math.max(f.endMs, end(s));
    tr.set(key(f.date, f.machine), (tr.get(key(f.date, f.machine)) ?? 0) + (s.assistant_msgs ?? 0));
  }
  for (const e of evs) {
    const f = e.session_id ? day.get(e.session_id) : undefined;
    if (e.name !== 'api_request' || !f || !IN_TRANSCRIPT(e.attrs.query_source) || e.ts > f.endMs + 60_000) continue;
    otel.set(key(f.date, f.machine), (otel.get(key(f.date, f.machine)) ?? 0) + 1);
  }
  const machines = [...new Set([...otel.keys(), ...tr.keys()].map((k) => k.split('|')[1]!))].sort();
  const rows: CoverageRow[] = [];
  for (const date of dates) for (const machine of machines) {
    const o = otel.get(key(date, machine)) ?? 0, t = tr.get(key(date, machine)) ?? 0;
    if (!o && !t) continue;
    const ratio = t ? o / t : null;
    rows.push({ date, machine, otel: o, transcript: t, ratio, grey: ratio != null && ratio < GREY_BELOW && date !== today });
  }
  const grey = dates.map((d) => rows.some((r) => r.date === d && r.grey));
  const combined = dates.map((d) => {
    const rs = rows.filter((r) => r.date === d);
    const t = rs.reduce((a, r) => a + r.transcript, 0);
    return t ? rs.reduce((a, r) => a + r.otel, 0) / t : null;
  });
  return { rows, grey, combined };
}

/** tool_decision counts per day for each source. */
export function toolDecisions(evs: Ev[], dates: string[]) {
  const by = Object.fromEntries(SOURCES.map((s) => [s, dates.map(() => 0)])) as Record<string, number[]>;
  for (const e of evs) {
    if (e.name !== 'tool_decision') continue;
    const i = dates.indexOf(e.date);
    const s = String(e.attrs.source);
    if (i >= 0 && by[s]) by[s]![i]!++;
  }
  return by;
}

const nearest = (sorted: number[], q: number) => sorted[Math.max(Math.ceil(q * sorted.length) - 1, 0)]!;
/** Hooks by total time spent: one entry per hook event + hashed name; p50/p95 over executions. */
export function hookTop(evs: Ev[], limit = 10) {
  const g = new Map<string, { event: string; name: string; ms: number[] }>();
  for (const e of evs) {
    if (e.name !== 'hook_execution_complete') continue;
    const event = String(e.attrs.hook_event ?? ''), name = String(e.attrs.hook_name ?? '');
    const k = event + '|' + name;
    const x = g.get(k) ?? { event, name, ms: [] };
    x.ms.push(Number(e.attrs.total_duration_ms) || 0);
    g.set(k, x);
  }
  return [...g.values()].map((x) => {
    const s = [...x.ms].sort((a, b) => a - b);
    return { event: x.event, name: x.name, count: s.length, total_ms: s.reduce((a, b) => a + b, 0), p50: nearest(s, 0.5), p95: nearest(s, 0.95) };
  }).sort((a, b) => b.total_ms - a.total_ms).slice(0, limit);
}

export type WaterfallRow = {
  offset_ms: number; ts: number; model: string; effort: string; input: number; output: number; cache_read: number; cache_create: number;
  duration_ms: number | null; ttft_ms: number | null; cost: number | null; query_source: string;
  tools: { tool: string; success: boolean; duration_ms: number | null }[]; errors: { error: string; status: string }[];
};
/** One row per api_request in time order, offsets from the first. tool_result / api_error attach by request_id, else to the latest earlier request of the same prompt. */
export function waterfall(evs: Ev[]): { rows: WaterfallRow[]; orphanErrors: Ev[] } {
  const sorted = [...evs].sort((a, b) => a.ts - b.ts);
  const reqs = sorted.filter((e) => e.name === 'api_request');
  const t0 = reqs[0]?.ts ?? 0;
  const n = (v: unknown) => (v == null || v === '' ? null : Number(v));
  const rows = reqs.map((e): WaterfallRow => ({
    offset_ms: e.ts - t0, ts: e.ts, model: String(e.attrs.model ?? 'unknown'), effort: e.attrs.effort || NOT_SET,
    input: n(e.attrs.input_tokens) ?? 0, output: n(e.attrs.output_tokens) ?? 0, cache_read: n(e.attrs.cache_read_tokens) ?? 0, cache_create: n(e.attrs.cache_creation_tokens) ?? 0,
    duration_ms: n(e.attrs.duration_ms), ttft_ms: n(e.attrs.ttft_ms), cost: n(e.attrs.cost_usd), query_source: String(e.attrs.query_source ?? ''), tools: [], errors: [],
  }));
  const byId = (e: Ev) => (e.request_id ? reqs.findIndex((r) => r.request_id === e.request_id) : -1);
  const owner = (e: Ev) => {
    const i = byId(e);
    if (i >= 0) return i;
    let last = -1;
    reqs.forEach((r, j) => { if (r.ts <= e.ts && (!e.prompt_id || r.prompt_id === e.prompt_id)) last = j; });
    return last;
  };
  const orphanErrors: Ev[] = [];
  for (const e of sorted) {
    if (e.name === 'tool_result') {
      const i = owner(e);
      if (i >= 0) rows[i]!.tools.push({ tool: String(e.attrs.tool_name ?? ''), success: String(e.attrs.success) !== 'false', duration_ms: n(e.attrs.duration_ms) });
    } else if (e.name === 'api_error') {
      const i = byId(e);
      if (i >= 0) rows[i]!.errors.push({ error: String(e.attrs.error ?? ''), status: String(e.attrs.status_code ?? '') });
      else orphanErrors.push(e);
    }
  }
  return { rows, orphanErrors };
}
