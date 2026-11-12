import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, it } from 'vitest';
import { callouts, concentration, friction, hooksByEvent, namedTools, q, readToolsTsv, routing, sourceKind, spendByKind, subagents, toolFamily, toolLatency, turns } from '../src/insights';
import type { Ev } from '../src/otel';

let t = 0;
const ev = (name: string, attrs: Record<string, unknown>, o: Partial<Ev> = {}): Ev => ({
  name, ts: 1_000_000 + (t += 1000), date: '2026-11-01', session_id: 's1', prompt_id: 'p1', request_id: null, machine: 'mac', attrs, ...o,
});
const req = (a: Record<string, unknown>, o: Partial<Ev> = {}) => ev('api_request', { model: 'opus', effort: 'medium', cost_usd: 0.1, duration_ms: 1000, query_source: 'repl_main_thread', ...a }, o);

it('quantiles are nearest-rank and null on empty', () => {
  expect(q([], 0.5)).toBeNull();
  expect(q([5, 1, 3], 0.5)).toBe(3);
  expect(q([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9)).toBe(9);
});

it('routing groups by model x effort with cost per request and cache hit', () => {
  const r = routing([
    req({ cost_usd: 0.2, cache_read_tokens: 90, cache_creation_tokens: 5, input_tokens: 5, ttft_ms: 500 }),
    req({ cost_usd: 0.4, cache_read_tokens: 0, cache_creation_tokens: 100, input_tokens: 0 }),
    req({ model: 'haiku', effort: undefined, cost_usd: 0.01 }),
  ]);
  expect(r.map((x) => [x.model, x.effort, x.n])).toEqual([['opus', 'medium', 2], ['haiku', 'not set', 1]]);
  expect(r[0]!.perReq).toBeCloseTo(0.3);
  expect(r[0]!.cacheHit).toBeCloseTo(90 / 200);
  expect(r[0]!.ttftP50).toBe(500);
});

it('spend splits by kind of call and shares add to 1', () => {
  expect(['repl_main_thread', 'agent:builtin:general-purpose', 'sdk', 'compact', 'web_search_tool', 'prompt_suggestion', 'away_summary'].map(sourceKind))
    .toEqual(['main conversation', 'subagents', 'headless (claude -p)', 'compaction', 'tool helpers (web search/fetch)', 'side calls (suggestions, summaries, titles)', 'side calls (suggestions, summaries, titles)']);
  const s = spendByKind([req({ cost_usd: 3 }), req({ cost_usd: 1, query_source: 'prompt_suggestion' })]);
  expect(s.map((x) => [x.kind, x.share])).toEqual([['main conversation', 0.75], ['side calls (suggestions, summaries, titles)', 0.25]]);
});

it('a turn is everything one typed prompt paid for; prompts without a user_prompt event are not turns', () => {
  const evs = [
    ev('user_prompt', {}, { prompt_id: 'p1' }), req({ cost_usd: 0.1 }, { prompt_id: 'p1' }), req({ cost_usd: 0.2 }, { prompt_id: 'p1' }),
    req({ cost_usd: 0.5, query_source: 'agent:x' }, { prompt_id: 'p1' }),
    ev('user_prompt', {}, { prompt_id: 'p2' }), req({ cost_usd: 1 }, { prompt_id: 'p2' }),
    req({ cost_usd: 9, query_source: 'sdk' }, { prompt_id: 'p3' }),
  ];
  const r = turns(evs);
  expect(r.prompts).toBe(2);
  expect(r.reqP90).toBe(2); // main-thread requests only
  expect(r.costMax).toBeCloseTo(1);
  expect(r.costP50).toBeCloseTo(0.8);
});

it('concentration: top tenth of sessions and the biggest ones', () => {
  const evs = Array.from({ length: 10 }, (_, i) => req({ cost_usd: i === 0 ? 10 : 1 }, { session_id: `s${i}` }));
  const c = concentration(evs, 2);
  expect(c.sessions).toBe(10);
  expect(c.top10share).toBeCloseTo(10 / 19);
  expect(c.top.map((x) => x.session)).toEqual(['s0', 's1']);
});

it('tool latency per tool and machine, failure rate and the commonest error', () => {
  const tr = (tool: string, ok: boolean, ms: number, machine = 'pc', err?: string) => ev('tool_result', { tool_name: tool, success: String(ok), duration_ms: String(ms), error_type: err, tool_result_size_bytes: '2048' }, { machine });
  const r = toolLatency([tr('Glob', false, 20000, 'pc', 'RipgrepTimeoutError'), tr('Glob', true, 4000), tr('Glob', false, 21000, 'pc', 'RipgrepTimeoutError'), tr('Glob', true, 10, 'mac')]);
  const pc = r.find((x) => x.tool === 'Glob' && x.machine === 'pc')!;
  expect(pc.n).toBe(3);
  expect(pc.failRate).toBeCloseTo(2 / 3);
  expect(pc.topError).toBe('RipgrepTimeoutError (2)');
  expect(pc.kbP50).toBe(2);
  expect(r.find((x) => x.machine === 'mac')!.failRate).toBe(0);
});

it('hooks by event, subagents, friction', () => {
  const h = hooksByEvent([
    ev('hook_execution_complete', { hook_event: 'PreToolUse', total_duration_ms: '600', num_blocking: '1' }),
    ev('hook_execution_complete', { hook_event: 'PreToolUse', total_duration_ms: '900', num_non_blocking_error: '1' }),
    ev('hook_execution_complete', { hook_event: 'Stop', total_duration_ms: '30' }),
  ]);
  expect(h[0]).toMatchObject({ event: 'PreToolUse', runs: 2, totalS: 1.5, maxMs: 900, blocking: 1, errors: 1 });
  const s = subagents([ev('subagent_completed', { agent_type: 'Explore', model: 'haiku', total_tokens: 100, total_tool_uses: 3, duration_ms: 4000 })]);
  expect(s[0]).toMatchObject({ type: 'Explore', n: 1, tokensTotal: 100, secP50: 4 });
  const f = friction([
    ev('permission_mode_changed', { from_mode: 'auto', to_mode: 'default', trigger: 'auto_gate_denied', 'terminal.type': 'non-interactive' }),
    ev('permission_mode_changed', { from_mode: 'auto', to_mode: 'default', trigger: 'auto_gate_denied', 'terminal.type': 'non-interactive' }),
    ev('tool_decision', { decision: 'reject', source: 'config', tool_name: 'Bash' }),
    ev('tool_decision', { decision: 'accept', source: 'config', tool_name: 'Bash' }),
    ev('compaction', { trigger: 'auto', pre_tokens: '167000', post_tokens: '30000', duration_ms: '45000' }),
  ]);
  expect(f.modeChanges).toEqual([{ from: 'auto', to: 'default', trigger: 'auto_gate_denied', terminal: 'non-interactive', n: 2 }]);
  expect(f.rejects).toEqual([{ tool: 'Bash', source: 'config', n: 1 }]);
  expect(f.compactions[0]).toMatchObject({ pre: 167000, post: 30000, sec: 45 });
});

it('callouts: only claims with enough samples; machine gap, failing tool, auto-mode drops', () => {
  const tr = (machine: string, ms: number, ok = true) => ev('tool_result', { tool_name: 'Bash', success: String(ok), duration_ms: String(ms), error_type: ok ? undefined : 'ShellError' }, { machine });
  const evs = [
    ...Array.from({ length: 20 }, (_, i) => tr('pc', 1300, i >= 4)), ...Array.from({ length: 20 }, () => tr('mac', 100)),
    ev('permission_mode_changed', { from_mode: 'auto', to_mode: 'default', trigger: 'auto_gate_denied' }),
  ];
  const texts = callouts(evs, []).map((c) => c.text);
  expect(texts).toContain('Bash runs 13× slower on the PC (median 1.30 s vs 100 ms).');
  expect(texts.some((x) => x.startsWith('Bash on the PC fails 20% of 20 calls; most common: ShellError (4)'))).toBe(true);
  expect(texts.some((x) => x.startsWith('Auto mode dropped to default 1 time(s)'))).toBe(true);
  expect(callouts(evs.slice(0, 5), []).filter((c) => c.text.includes('slower'))).toEqual([]);
});

it('tools.tsv: both machines, families named, error rate per tool', () => {
  const dir = mkdtempSync(join(tmpdir(), 'obs-tools-'));
  mkdirSync(join(dir, 'pc'));
  const head = '# x\n# session\tdate\tproject\tagent\ttool\tcalls\terrors\tdenials\tresult_bytes\n';
  writeFileSync(join(dir, 'tools.tsv'), head + 'a\t2026-11-01\tp\tmain\tmcp__claude_ai_Indeed__search_jobs\t10\t2\t0\t1000\na/x\t2026-11-01\tp\tsubagent:x\tBash\t4\t0\t1\t10\n');
  writeFileSync(join(dir, 'pc', 'tools.tsv'), head + 'b\t2026-11-01\t-private-tmp-x\theadless\tmcp__claude_ai_Indeed__search_jobs\t10\t0\t0\t0\n');
  const rows = readToolsTsv(dir);
  expect(rows.map((r) => [r.machine, r.scratch])).toEqual([['mac', false], ['mac', false], ['pc', true]]);
  const n = namedTools(rows);
  expect(n[0]).toMatchObject({ family: 'MCP Indeed', name: 'search_jobs', calls: 20, errors: 2, errRate: 0.1, sessions: 2 });
  expect(toolFamily('Skill:bacon:greet')).toEqual({ family: 'Skill', name: 'bacon:greet' });
  expect(toolFamily('/clear')).toEqual({ family: 'Slash command', name: '/clear' });
});
