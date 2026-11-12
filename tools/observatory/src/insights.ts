import type { Database } from 'better-sqlite3';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Ev } from './otel';
import { isScratch } from './project';

// Window aggregates: one number per group over the whole window, where per-day lines are too thin to read.

const N = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : 0; };
/** Nearest-rank quantile; null on an empty list. */
export function q(xs: number[], p: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.max(Math.ceil(p * s.length) - 1, 0)]!;
}
const group = <T>(xs: T[], key: (x: T) => string) => {
  const m = new Map<string, T[]>();
  for (const x of xs) { const k = key(x); (m.get(k) ?? m.set(k, []).get(k)!).push(x); }
  return m;
};
const reqs = (evs: Ev[]) => evs.filter((e) => e.name === 'api_request');
const cost = (e: Ev) => N(e.attrs.cost_usd);

export type RouteRow = { model: string; effort: string; n: number; cost: number; perReq: number; outP50: number | null; durP50: number | null; durP90: number | null; ttftP50: number | null; cacheHit: number | null };
/** api_request by model x effort: what each routing choice costs and how fast it answers. */
export function routing(evs: Ev[]): RouteRow[] {
  return [...group(reqs(evs), (e) => `${e.attrs.model ?? 'unknown'}\u0000${e.attrs.effort || 'not set'}`)].map(([k, xs]) => {
    const [model, effort] = k.split('\u0000') as [string, string];
    const c = xs.reduce((a, e) => a + cost(e), 0);
    const read = xs.reduce((a, e) => a + N(e.attrs.cache_read_tokens), 0);
    const all = read + xs.reduce((a, e) => a + N(e.attrs.cache_creation_tokens) + N(e.attrs.input_tokens), 0);
    const ttft = xs.filter((e) => e.attrs.ttft_ms != null).map((e) => N(e.attrs.ttft_ms));
    return {
      model, effort, n: xs.length, cost: c, perReq: c / xs.length,
      outP50: q(xs.map((e) => N(e.attrs.output_tokens)), 0.5),
      durP50: q(xs.map((e) => N(e.attrs.duration_ms)), 0.5), durP90: q(xs.map((e) => N(e.attrs.duration_ms)), 0.9),
      ttftP50: q(ttft, 0.5), cacheHit: all ? read / all : null,
    };
  }).sort((a, b) => b.cost - a.cost);
}

/** query_source -> what kind of spend it is. */
export function sourceKind(qs: unknown): string {
  const s = String(qs ?? '');
  if (s === '' || s === 'repl_main_thread') return 'main conversation';
  if (s.startsWith('agent:')) return 'subagents';
  if (s === 'sdk') return 'headless (claude -p)';
  if (s === 'compact') return 'compaction';
  if (s.endsWith('_tool') || s.startsWith('web_')) return 'tool helpers (web search/fetch)';
  return 'side calls (suggestions, summaries, titles)';
}
export type SpendRow = { kind: string; n: number; cost: number; share: number; sources: string[] };
export function spendByKind(evs: Ev[]): SpendRow[] {
  const rs = reqs(evs);
  const total = rs.reduce((a, e) => a + cost(e), 0);
  return [...group(rs, (e) => sourceKind(e.attrs.query_source))].map(([kind, xs]) => {
    const c = xs.reduce((a, e) => a + cost(e), 0);
    return { kind, n: xs.length, cost: c, share: total ? c / total : 0, sources: [...new Set(xs.map((e) => String(e.attrs.query_source ?? '')))].sort() };
  }).sort((a, b) => b.cost - a.cost);
}

export type Turns = { prompts: number; reqP50: number | null; reqP90: number | null; costP50: number | null; costP90: number | null; costMax: number | null; secP50: number | null; secP90: number | null };
/** One typed prompt = everything its prompt_id paid for, main thread and subagents together. */
export function turns(evs: Ev[]): Turns {
  const byPrompt = group(reqs(evs).filter((e) => e.prompt_id), (e) => e.prompt_id!);
  const typed = new Set(evs.filter((e) => e.name === 'user_prompt' && e.prompt_id).map((e) => e.prompt_id!));
  const ps = [...byPrompt].filter(([id]) => typed.has(id)).map(([, xs]) => xs);
  const c = ps.map((xs) => xs.reduce((a, e) => a + cost(e), 0));
  const r = ps.map((xs) => xs.filter((e) => sourceKind(e.attrs.query_source) === 'main conversation').length);
  const secs = ps.map((xs) => (Math.max(...xs.map((e) => e.ts)) - Math.min(...xs.map((e) => e.ts - N(e.attrs.duration_ms)))) / 1000);
  return { prompts: ps.length, reqP50: q(r, 0.5), reqP90: q(r, 0.9), costP50: q(c, 0.5), costP90: q(c, 0.9), costMax: c.length ? Math.max(...c) : null, secP50: q(secs, 0.5), secP90: q(secs, 0.9) };
}

export type Concentration = { sessions: number; total: number; top10share: number | null; top: { session: string; machine: string; cost: number; share: number; requests: number }[] };
/** How much of the spend sits in the few biggest sessions. */
export function concentration(evs: Ev[], limit = 5): Concentration {
  const by = [...group(reqs(evs).filter((e) => e.session_id), (e) => e.session_id!)].map(([session, xs]) => ({ session, machine: xs[0]!.machine ?? '?', cost: xs.reduce((a, e) => a + cost(e), 0), requests: xs.length }));
  by.sort((a, b) => b.cost - a.cost);
  const total = by.reduce((a, x) => a + x.cost, 0);
  const k = Math.max(1, Math.ceil(by.length / 10));
  return {
    sessions: by.length, total, top10share: total ? by.slice(0, k).reduce((a, x) => a + x.cost, 0) / total : null,
    top: by.slice(0, limit).map((x) => ({ ...x, share: total ? x.cost / total : 0 })),
  };
}

export type ToolRow = { tool: string; machine: string; n: number; failRate: number; topError: string | null; p50: number | null; p90: number | null; kbP50: number | null };
/** tool_result by tool and machine: how often it fails, why, and how long it blocks. */
export function toolLatency(evs: Ev[]): ToolRow[] {
  const rs = evs.filter((e) => e.name === 'tool_result');
  return [...group(rs, (e) => `${e.attrs.tool_name ?? '?'}\u0000${e.machine ?? '?'}`)].map(([k, xs]) => {
    const [tool, machine] = k.split('\u0000') as [string, string];
    const fails = xs.filter((e) => String(e.attrs.success) !== 'true');
    const errs = [...group(fails, (e) => String(e.attrs.error_type ?? 'unknown'))].sort((a, b) => b[1].length - a[1].length);
    return {
      tool, machine, n: xs.length, failRate: fails.length / xs.length,
      topError: errs[0] ? `${errs[0][0]} (${errs[0][1].length})` : null,
      p50: q(xs.map((e) => N(e.attrs.duration_ms)), 0.5), p90: q(xs.map((e) => N(e.attrs.duration_ms)), 0.9),
      kbP50: q(xs.map((e) => N(e.attrs.tool_result_size_bytes) / 1024), 0.5),
    };
  }).sort((a, b) => b.n - a.n);
}

export type HookEventRow = { event: string; runs: number; totalS: number; p50: number | null; p90: number | null; maxMs: number; blocking: number; errors: number };
/** Hook time per event: what each tool call or prompt waits for. */
export function hooksByEvent(evs: Ev[]): HookEventRow[] {
  return [...group(evs.filter((e) => e.name === 'hook_execution_complete'), (e) => String(e.attrs.hook_event ?? '?'))].map(([event, xs]) => {
    const ms = xs.map((e) => N(e.attrs.total_duration_ms));
    return {
      event, runs: xs.length, totalS: ms.reduce((a, b) => a + b, 0) / 1000, p50: q(ms, 0.5), p90: q(ms, 0.9), maxMs: Math.max(...ms),
      blocking: xs.reduce((a, e) => a + N(e.attrs.num_blocking), 0), errors: xs.reduce((a, e) => a + N(e.attrs.num_non_blocking_error), 0),
    };
  }).sort((a, b) => b.totalS - a.totalS);
}

export type SubagentRow = { type: string; model: string; n: number; tokensP50: number | null; tokensTotal: number; toolsP50: number | null; secP50: number | null };
export function subagents(evs: Ev[]): SubagentRow[] {
  return [...group(evs.filter((e) => e.name === 'subagent_completed'), (e) => `${e.attrs.agent_type ?? '?'}\u0000${e.attrs.model ?? '?'}`)].map(([k, xs]) => {
    const [type, model] = k.split('\u0000') as [string, string];
    const tok = xs.map((e) => N(e.attrs.total_tokens));
    return { type, model, n: xs.length, tokensP50: q(tok, 0.5), tokensTotal: tok.reduce((a, b) => a + b, 0), toolsP50: q(xs.map((e) => N(e.attrs.total_tool_uses)), 0.5), secP50: (q(xs.map((e) => N(e.attrs.duration_ms)), 0.5) ?? 0) / 1000 };
  }).sort((a, b) => b.n - a.n);
}

export type Friction = { compactions: { date: string; trigger: string; pre: number; post: number; sec: number }[]; modeChanges: { from: string; to: string; trigger: string; terminal: string; n: number }[]; rejects: { tool: string; source: string; n: number }[] };
/** Things that interrupt work: compactions, permission-mode drops, refused tool calls. */
export function friction(evs: Ev[]): Friction {
  const compactions = evs.filter((e) => e.name === 'compaction').map((e) => ({ date: e.date, trigger: String(e.attrs.trigger ?? ''), pre: N(e.attrs.pre_tokens), post: N(e.attrs.post_tokens), sec: N(e.attrs.duration_ms) / 1000 }));
  const modeChanges = [...group(evs.filter((e) => e.name === 'permission_mode_changed'), (e) => [e.attrs.from_mode, e.attrs.to_mode, e.attrs.trigger, e.attrs['terminal.type']].join('\u0000'))]
    .map(([k, xs]) => { const [from, to, trigger, terminal] = k.split('\u0000') as [string, string, string, string]; return { from, to, trigger, terminal, n: xs.length }; })
    .sort((a, b) => b.n - a.n);
  const rejects = [...group(evs.filter((e) => e.name === 'tool_decision' && e.attrs.decision !== 'accept'), (e) => `${e.attrs.tool_name ?? '?'}\u0000${e.attrs.source ?? '?'}`)]
    .map(([k, xs]) => { const [tool, source] = k.split('\u0000') as [string, string]; return { tool, source, n: xs.length }; })
    .sort((a, b) => b.n - a.n);
  return { compactions, modeChanges, rejects };
}

export type Output = { added: number; removed: number; commits: number; prs: number };
/** Lines, commits and PRs Claude Code counted (OTel metrics), ts in [fromMs, toMs]. */
export function outputTotals(db: Database, fromMs: number, toMs: number, machine: string): Output {
  const rows = db.prepare(`SELECT name, value, attrs, machine FROM otel_metrics WHERE ts BETWEEN ? AND ? AND name IN
    ('claude_code.lines_of_code.count', 'claude_code.commit.count', 'claude_code.pull_request.count')`).all(fromMs, toMs) as { name: string; value: number; attrs: string; machine: string }[];
  const o: Output = { added: 0, removed: 0, commits: 0, prs: 0 };
  for (const r of rows) {
    if (machine !== 'all' && r.machine !== machine) continue;
    if (r.name.endsWith('commit.count')) o.commits += N(r.value);
    else if (r.name.endsWith('pull_request.count')) o.prs += N(r.value);
    else {
      let type = '';
      try { type = JSON.parse(r.attrs).type; } catch { /* skip */ }
      if (type === 'added') o.added += N(r.value); else if (type === 'removed') o.removed += N(r.value);
    }
  }
  return o;
}

export type Callout ={ tone: 'warn' | 'info'; text: string };
const pctS = (x: number) => `${Math.round(x * 100)}%`;
/** 3 ms, 210 ms, 1.36 s, 21 s */
export const dur = (ms: number) => (ms < 1000 ? `${Math.round(ms)} ms` : ms < 10000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms / 1000)} s`);
/** Plain sentences for what stands out in the window; only claims backed by at least MIN samples. */
export function callouts(evs: Ev[], named: NamedToolRow[], MIN = 20): Callout[] {
  const out: Callout[] = [];
  const spend = spendByKind(evs);
  const side = spend.filter((s) => s.kind.startsWith('side calls') || s.kind === 'compaction').reduce((a, s) => a + s.share, 0);
  if (side >= 0.03) out.push({ tone: 'info', text: `${pctS(side)} of spend is overhead: side calls (suggestions, summaries, titles) and compaction.` });
  const c = concentration(evs);
  if (c.sessions >= 10 && c.top10share != null && c.top10share >= 0.4) out.push({ tone: 'info', text: `The top tenth of sessions (${Math.ceil(c.sessions / 10)} of ${c.sessions}) hold ${pctS(c.top10share)} of spend; read averages with that in mind.` });
  const lat = toolLatency(evs);
  let worst: { tool: string; ratio: number; slow: string; a: number; b: number } | null = null;
  for (const r of lat.filter((r) => r.machine === 'pc' && r.n >= MIN)) {
    const m = lat.find((x) => x.tool === r.tool && x.machine === 'mac' && x.n >= MIN);
    if (!m || !m.p50 || !r.p50) continue;
    const [ratio, slow, a, b] = r.p50 >= m.p50 ? [r.p50 / m.p50, 'PC', r.p50, m.p50] : [m.p50 / r.p50, 'Mac', m.p50, r.p50];
    if (ratio >= 3 && (a as number) >= 500 && (!worst || ratio > worst.ratio)) worst = { tool: r.tool, ratio, slow: slow as string, a: a as number, b: b as number };
  }
  if (worst) out.push({ tone: 'warn', text: `${worst.tool} runs ${worst.ratio.toFixed(0)}× slower on the ${worst.slow} (median ${dur(worst.a)} vs ${dur(worst.b)}).` });
  for (const r of lat.filter((r) => r.n >= MIN && r.failRate >= 0.1).slice(0, 3)) out.push({ tone: 'warn', text: `${r.tool} on the ${r.machine === 'pc' ? 'PC' : 'Mac'} fails ${pctS(r.failRate)} of ${r.n} calls; most common: ${r.topError}.` });
  for (const t of named.filter((t) => t.calls >= MIN && t.errRate >= 0.1 && t.family !== 'Built-in').slice(0, 3)) out.push({ tone: 'warn', text: `${t.family} ${t.name} errors on ${pctS(t.errRate)} of ${t.calls} calls (transcripts).` });
  const drops = friction(evs).modeChanges.filter((m) => m.trigger === 'auto_gate_denied').reduce((a, m) => a + m.n, 0);
  if (drops) out.push({ tone: 'warn', text: `Auto mode dropped to default ${drops} time(s) because its gate denied a call; in headless runs that means the run could not finish unattended.` });
  const h = hooksByEvent(evs).filter((x) => x.event === 'PreToolUse' || x.event === 'PostToolUse');
  const wait = h.reduce((a, x) => a + (x.p50 ?? 0), 0);
  if (wait >= 500) out.push({ tone: 'info', text: `Hooks add about ${(wait / 1000).toFixed(1)} s to a typical tool call (median PreToolUse + PostToolUse).` });
  return out;
}

// ---- tools.tsv (transcripts): names OTel does not carry (MCP server and tool, skill, slash command), full history.
export type ToolTsvRow = { session: string; date: string; project: string; agent: string; tool: string; calls: number; errors: number; denials: number; result_bytes: number; machine: string; scratch: boolean };
export function readToolsTsv(dir: string): ToolTsvRow[] {
  const out: ToolTsvRow[] = [];
  for (const [machine, sub] of [['mac', ''], ['pc', 'pc/']] as const) {
    const p = join(dir, sub, 'tools.tsv');
    if (!existsSync(p)) continue;
    const lines = readFileSync(p, 'utf8').split(/\r?\n/);
    const header = lines.filter((l) => l.startsWith('# ')).pop()?.slice(2).split('\t') ?? [];
    for (const l of lines) {
      if (!l.trim() || l.startsWith('#')) continue;
      const r = Object.fromEntries(header.map((h, i) => [h, l.split('\t')[i] ?? '']));
      out.push({ session: r.session!, date: r.date!, project: r.project!, agent: r.agent!, tool: r.tool!, calls: N(r.calls), errors: N(r.errors), denials: N(r.denials), result_bytes: N(r.result_bytes), machine, scratch: isScratch(r.project!) });
    }
  }
  return out;
}

/** mcp__<server>__<tool> -> "<server>" / "<tool>"; claude.ai connectors drop their claude_ai_ prefix. */
export function toolFamily(tool: string): { family: string; name: string } {
  const m = /^mcp__(.+?)__(.+)$/.exec(tool);
  if (m) return { family: `MCP ${m[1]!.replace(/^claude_ai_/, '')}`, name: m[2]! };
  if (tool.startsWith('Skill:')) return { family: 'Skill', name: tool.slice(6) };
  if (tool.startsWith('Agent:')) return { family: 'Subagent', name: tool.slice(6) };
  if (tool.startsWith('/')) return { family: 'Slash command', name: tool };
  return { family: 'Built-in', name: tool };
}

export type NamedToolRow = { family: string; name: string; calls: number; errors: number; denials: number; errRate: number; sessions: number; mb: number };
export function namedTools(rows: ToolTsvRow[]): NamedToolRow[] {
  return [...group(rows, (r) => r.tool)].map(([tool, xs]) => {
    const calls = xs.reduce((a, r) => a + r.calls, 0), errors = xs.reduce((a, r) => a + r.errors, 0);
    return { ...toolFamily(tool), calls, errors, denials: xs.reduce((a, r) => a + r.denials, 0), errRate: calls ? errors / calls : 0, sessions: new Set(xs.map((r) => r.session.split('/')[0])).size, mb: xs.reduce((a, r) => a + r.result_bytes, 0) / 1e6 };
  }).sort((a, b) => b.calls - a.calls);
}
