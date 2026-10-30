import { expect, it } from 'vitest';
import { computeTiles, type Filters, type SessionRow, type UsageRow } from '../src/metrics';

let n = 0;
const s = (o: Partial<SessionRow> = {}): SessionRow => ({
  session: `s${n++}`, date: '2026-10-08', machine: 'mac', scratch: 0, agent_kind: 'interactive', active_s: 3600, assistant_msgs: 10,
  interruptions: 0, tool_errors: 0, denials: 0, tokens_in: 0, tokens_out: 0, cache_read: 0, cache_create: 0, model: 'opus', ...o,
});
const u = (o: Partial<UsageRow> = {}): UsageRow => ({
  session: 's0', date: '2026-10-08', machine: 'mac', scratch: 0, agent: 'main', requests: 1, cost_usd: 0, effort: 'high', ...o,
});
const f: Filters = { machine: 'all', scratch: false, agent: 'all', days: 10, today: '2026-10-10' };
const tile = (id: string, ss: SessionRow[], uu: UsageRow[] = [], ff = f) =>
  computeTiles(ss, uu, ff, '2026-10-28').find((t) => t.id === id)!;
const at = (t: { dates: string[]; series: (number | null)[] }, d: string) => t.series[t.dates.indexOf(d)];

it('covers the window with one point per day', () => {
  const t = tile('sessions', []);
  expect(t.dates[0]).toBe('2026-10-01');
  expect(t.dates.at(-1)).toBe('2026-10-10');
  expect(t.series).toHaveLength(10);
});

it('counts main sessions only, hides scratch, filters machine', () => {
  const ss = [s(), s(), s({ session: 'x/agent' }), s({ scratch: 1 }), s({ machine: 'pc' }), s({ date: '2026-09-01' })];
  expect(at(tile('sessions', ss), '2026-10-08')).toBe(3);
  expect(tile('sessions', ss, [], { ...f, scratch: true }).series.reduce((a, b) => a! + b!, 0)).toBe(4);
  expect(at(tile('sessions', ss, [], { ...f, machine: 'pc' }), '2026-10-08')).toBe(1);
  expect(tile('sessions', ss).value).toBeCloseTo(3 / 7); // per day, last 7 days
});

it('sums active hours of main sessions', () => {
  const t = tile('active', [s({ active_s: 5400 }), s({ active_s: 1800 }), s({ session: 'x/a', active_s: 9999 })]);
  expect(at(t, '2026-10-08')).toBe(2);
});

it('sums denials per day', () => {
  expect(at(tile('denials', [s({ denials: 2 }), s({ denials: 3 })]), '2026-10-08')).toBe(5);
});

it('pools ratio tiles and reports IQR, largest share and low-n', () => {
  const five = [10, 10, 10, 10, 60].map((m, i) => s({ assistant_msgs: m, tool_errors: i === 4 ? 6 : 0 }));
  const two = [s({ date: '2026-10-09', assistant_msgs: 10, tool_errors: 5 }), s({ date: '2026-10-09', assistant_msgs: 10, tool_errors: 5 })];
  const t = tile('toolErrors', [...five, ...two]);
  expect(at(t, '2026-10-08')).toBeCloseTo(6); // pooled 6 errors / 100 msgs, not mean of ratios (2)
  const d = t.ratio!.perDay[t.dates.indexOf('2026-10-08')]!;
  expect(d.n).toBe(5);
  expect(d.largestShare).toBeCloseTo(0.6);
  expect(d.iqr).toEqual([0, 0]);
  expect(d.lowN).toBe(false);
  const low = t.ratio!.perDay[t.dates.indexOf('2026-10-09')]!;
  expect(low.lowN).toBe(true);
  expect(at(t, '2026-10-09')).toBeNull();
  expect(t.value).toBeCloseTo((16 / 120) * 100); // pooled over the 7 days incl. low-n
  expect(t.ratio!.lastLargestShare).toBeCloseTo(0.5); // last day with data: two equal sessions
});

it('interruptions per active hour', () => {
  const ss = Array.from({ length: 5 }, (_, i) => s({ interruptions: i, active_s: 3600 }));
  expect(at(tile('interruptions', ss), '2026-10-08')).toBe(2); // 10 / 5h
});

it('cache hit ratio = read / (read + create + in)', () => {
  const ss = Array.from({ length: 5 }, () => s({ cache_read: 80, cache_create: 15, tokens_in: 5 }));
  expect(at(tile('cache', ss), '2026-10-08')).toBeCloseTo(0.8);
});

it('tokens and cost by model', () => {
  const ss = [
    s({ session: 'a', model: 'opus', tokens_in: 1, tokens_out: 2, cache_read: 3, cache_create: 4 }),
    s({ session: 'b', model: 'opus', tokens_in: 10 }),
    s({ session: 'c', model: 'haiku', tokens_out: 5 }),
    s({ session: 'd', model: null, tokens_out: 99 }),
  ];
  const uu = [u({ session: 'a', cost_usd: 1.5 }), u({ session: 'a', cost_usd: 0.5 }), u({ session: 'c', cost_usd: 0.25 })];
  const t = tile('models', ss, uu);
  expect(t.byModel).toEqual([
    { model: 'opus', tokens: 20, cost: 2, n: 2 },
    { model: 'haiku', tokens: 5, cost: 0.25, n: 1 },
  ]);
  expect(t.explanation).toContain('2026-10-28');
});

it('effort mix is a share of requests per day, empty = not set', () => {
  const t = tile('effort', [], [u({ requests: 3, effort: 'high' }), u({ requests: 1, effort: '' })]);
  expect(at({ dates: t.dates, series: t.effort!['high']! }, '2026-10-08')).toBeCloseTo(0.75);
  expect(at({ dates: t.dates, series: t.effort!['not set']! }, '2026-10-08')).toBeCloseTo(0.25);
  expect(t.effort!['high']![0]).toBeNull();
});

it('agent filter: interactive (default intent) = interactive + subagent; headless = headless + hook; unknown only under all', () => {
  const ss = [s({ agent_kind: 'interactive' }), s({ agent_kind: 'subagent', session: 'x/a' }), s({ agent_kind: 'headless' }), s({ agent_kind: 'hook' }), s({ agent_kind: 'unknown' })];
  const day = (agent: Filters['agent']) => at(tile('sessions', ss, [], { ...f, agent }), '2026-10-08');
  expect(day('interactive')).toBe(1); // subagent rows are not main sessions
  expect(day('headless')).toBe(2);
  expect(day('all')).toBe(4);
  const uu = [u({ agent: 'main' }), u({ agent: 'subagent:Explore' }), u({ agent: 'headless' }), u({ agent: 'hook:x', effort: 'low' })];
  expect(tile('effort', [], uu, { ...f, agent: 'headless' }).effort).toHaveProperty('low');
  expect(tile('effort', [], uu, { ...f, agent: 'interactive' }).effort).not.toHaveProperty('low');
});
