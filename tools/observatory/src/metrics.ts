export const MIN_N = 5;

export type SessionRow = {
  session: string; date: string; machine: string; scratch: number; active_s: number | null; assistant_msgs: number | null;
  interruptions: number | null; tool_errors: number | null; denials: number | null; tokens_in: number | null;
  tokens_out: number | null; cache_read: number | null; cache_create: number | null; model: string | null;
  agent_kind: string; project?: string; started?: string | null; ended?: string | null; duration_s?: number | null;
};
export type UsageRow = {
  session: string; date: string; machine: string; scratch: number; agent: string; requests: number | null; cost_usd: number | null; effort: string | null;
};
export type Filters = { machine: 'all' | 'mac' | 'pc'; scratch: boolean; agent: 'interactive' | 'headless' | 'all'; days: number; today: string };
export type DayStat = { n: number; largestShare: number | null; iqr: [number, number] | null; lowN: boolean };
export type Tile = {
  id: string; title: string; unit: string; explanation: string; reading: string; source: string; n: number;
  value: number | null; prev: number | null; dates: string[]; series: (number | null)[];
  effortRequests?: number[];
  ratio?: { perDay: DayStat[]; lastLargestShare: number | null; iqr: ([number, number] | null)[] };
  byModel?: { model: string; tokens: number; cost: number; n: number }[];
  effort?: Record<string, (number | null)[]>;
};

const DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const v = (x: number | null) => x ?? 0;
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
const isMain = (r: { session: string }) => !r.session.includes('/');

function quantile(sorted: number[], q: number) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  return sorted[lo]! + (sorted[Math.min(lo + 1, sorted.length - 1)]! - sorted[lo]!) * (pos - lo);
}

export function computeTiles(allSessions: SessionRow[], allUsage: UsageRow[], f: Filters, pricesAsOf: string | null): Tile[] {
  const end = Date.parse(f.today);
  const dates = Array.from({ length: f.days }, (_, i) => iso(end - (f.days - 1 - i) * DAY));
  const last7 = new Set(dates.slice(-7));
  const prevDates = Array.from({ length: 7 }, (_, i) => iso(end - (13 - i) * DAY));
  const keepRow = (r: { machine: string; scratch: number }) => (f.machine === 'all' || r.machine === f.machine) && (f.scratch || !r.scratch);
  const keep = (r: { date: string; machine: string; scratch: number }) => dates.includes(r.date) && keepRow(r);
  const kinds = { interactive: ['interactive', 'subagent'], headless: ['headless', 'hook'] }[f.agent as 'interactive'];
  const kindOk = (r: SessionRow) => !kinds || kinds.includes(r.agent_kind);
  const ss = allSessions.filter((r) => keep(r) && kindOk(r));
  // Previous week: only trusted when loaded data reaches back to its first day.
  const earliest = allSessions.filter((r) => keepRow(r) && kindOk(r)).map((r) => r.date).sort()[0];
  const prevRows = earliest !== undefined && earliest <= prevDates[0]! ? allSessions.filter((r) => prevDates.includes(r.date) && keepRow(r) && kindOk(r)) : null;
  const uu = allUsage.filter((r) => keep(r) && (f.agent === 'all' || (f.agent === 'headless') === (r.agent === 'headless' || r.agent.startsWith('hook:'))));
  const byDay = <T extends { date: string }>(rows: T[]) => dates.map((d) => rows.filter((r) => r.date === d));
  const sessionsByDay = byDay(ss);
  const main = sessionsByDay.map((rows) => rows.filter(isMain));

  // Tiles that add something up per day: value = average per day over the last 7 days.
  const perDay = (id: string, title: string, unit: string, explanation: string, reading: string, source: string, pick: (r: SessionRow) => number): Tile => {
    const series = main.map((rows) => sum(rows.map(pick)));
    const week = series.filter((_, i) => last7.has(dates[i]!));
    return { id, title, unit, explanation, reading, source, n: main.flat().length, value: sum(week) / 7, prev: prevRows && sum(prevRows.filter(isMain).map(pick)) / 7, dates, series };
  };

  // Ratio tiles: pooled (sum numerators / sum denominators), plus spread and concentration per day.
  const ratio = (id: string, title: string, unit: string, explanation: string, reading: string, source: string, scale: number, num: (r: SessionRow) => number, den: (r: SessionRow) => number): Tile => {
    const stats = sessionsByDay.map((rows) => {
      const used = rows.filter((r) => den(r) > 0);
      const d = sum(used.map(den));
      const rs = used.map((r) => (num(r) / den(r)) * scale).sort((a, b) => a - b);
      const lowN = used.length < MIN_N;
      return {
        point: used.length && !lowN ? (sum(used.map(num)) / d) * scale : null,
        stat: {
          n: used.length, lowN,
          largestShare: used.length ? Math.max(...used.map(den)) / d : null,
          iqr: used.length ? ([quantile(rs, 0.25), quantile(rs, 0.75)] as [number, number]) : null,
        } satisfies DayStat,
      };
    });
    const weekRows = sessionsByDay.filter((_, i) => last7.has(dates[i]!)).flat().filter((r) => den(r) > 0);
    const d = sum(weekRows.map(den));
    const lastIdx = stats.map((x) => x.stat.n > 0).lastIndexOf(true);
    const pw = prevRows?.filter((r) => den(r) > 0) ?? [];
    const pd = sum(pw.map(den));
    return {
      id, title, unit, explanation, reading, source, n: sessionsByDay.flat().filter((r) => den(r) > 0).length,
      value: d > 0 ? (sum(weekRows.map(num)) / d) * scale : null,
      prev: pw.length >= MIN_N ? (sum(pw.map(num)) / pd) * scale : null, dates, series: stats.map((x) => x.point),
      ratio: { perDay: stats.map((x) => x.stat), lastLargestShare: lastIdx < 0 ? null : stats[lastIdx]!.stat.largestShare, iqr: stats.map((x) => x.stat.iqr) },
    };
  };

  // Tokens and cost by model, over the whole window.
  const cost = new Map<string, number>();
  for (const r of uu) cost.set(r.session, (cost.get(r.session) ?? 0) + v(r.cost_usd));
  const models = new Map<string, { model: string; tokens: number; cost: number; n: number }>();
  for (const r of ss) {
    if (!r.model) continue;
    const m = models.get(r.model) ?? { model: r.model, tokens: 0, cost: 0, n: 0 };
    m.tokens += v(r.tokens_in) + v(r.tokens_out) + v(r.cache_read) + v(r.cache_create);
    m.cost += cost.get(r.session) ?? 0;
    m.n++;
    models.set(r.model, m);
  }
  const byModel = [...models.values()].sort((a, b) => b.tokens - a.tokens);

  // Effort mix: share of requests per effort per day.
  const efforts = [...new Set(uu.map((r) => r.effort || 'not set'))].sort();
  const usageByDay = byDay(uu);
  const effort = Object.fromEntries(efforts.map((e) => [e, usageByDay.map((rows) => {
    const total = sum(rows.map((r) => v(r.requests)));
    return total ? sum(rows.filter((r) => (r.effort || 'not set') === e).map((r) => v(r.requests))) / total : null;
  })]));

  return [
    perDay('sessions', 'Sessions per day', 'sessions/day', 'Main conversations started that day; subagent runs inside a session are not counted.',
      'Volume only. Subagent runs inside a session are not counted.',
      'sessions.tsv: session, date', () => 1),
    perDay('active', 'Active hours per day', 'h/day', 'Time I spent actively working in main sessions (gaps while idle are not counted), in hours.',
      'More hours with flat sessions = longer sessions.',
      'sessions.tsv: active_s', (r) => v(r.active_s) / 3600),
    {
      id: 'models', title: 'Tokens and cost by model', unit: 'tokens', n: ss.filter((r) => r.model).length, value: sum(byModel.map((m) => m.tokens)), prev: null,
      explanation: `Input, output and cache tokens per model, with estimated dollars (estimate, list price as of ${pricesAsOf ?? 'unknown'}).`,
      reading: 'Cost is an estimate at list price, not the bill.',
      source: 'sessions.tsv: model, tokens_in, tokens_out, cache_read, cache_create; usage.tsv: cost_usd',
      dates, series: [], byModel,
    },
    {
      id: 'effort', title: 'Effort mix over time', unit: 'share', n: new Set(uu.map((r) => r.session)).size, value: null, prev: null,
      explanation: 'Share of requests made at each effort level per day; "not set" means the level was not recorded.',
      reading: 'Shows routing changes; "not set" = not recorded.',
      source: 'usage.tsv: effort, requests', dates, series: [], effort,
      effortRequests: usageByDay.map((rows) => sum(rows.map((r) => v(r.requests)))),
    },
    ratio('toolErrors', 'Tool error rate', 'per 100 requests', 'Failed tool calls per 100 assistant requests; days with fewer than 5 sessions are greyed out.',
      'Up after a harness change = that change broke something; check the markers.',
      'sessions.tsv: tool_errors, assistant_msgs', 100, (r) => v(r.tool_errors), (r) => v(r.assistant_msgs)),
    ratio('interruptions', 'Interruptions per active hour', 'per hour', 'Messages I queued while the assistant was working, per hour of active work (a stand-in for stopping it mid-turn).',
      'Up = he stops me more often, a sign of wrong direction.',
      'sessions.tsv: interruptions, active_s', 1, (r) => v(r.interruptions), (r) => v(r.active_s) / 3600),
    perDay('denials', 'Denials per day', 'denials/day', 'Tool calls the permission system or I refused, summed per day.',
      'Up = I am asking for things outside the rules.',
      'sessions.tsv: denials', (r) => v(r.denials)),
    ratio('cache', 'Cache hit ratio', 'ratio', 'Share of input served from cache: cache reads divided by cache reads, cache writes and fresh input.',
      'Down = more context rebuilt (idle gaps, compactions, model switches) = more cost.',
      'sessions.tsv: cache_read, cache_create, tokens_in', 1, (r) => v(r.cache_read), (r) => v(r.cache_read) + v(r.cache_create) + v(r.tokens_in)),
  ];
}
