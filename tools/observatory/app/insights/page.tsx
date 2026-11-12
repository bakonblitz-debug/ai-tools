import { callouts, concentration, dur, friction, hooksByEvent, namedTools, outputTotals, readToolsTsv, routing, spendByKind, subagents, toolLatency, turns } from '../../src/insights';
import { filterEvents, loadEvents, openOtel } from '../../src/otel';
import { href, tz } from '../../src/query';
import { loadCtx, METRICS_DIR } from '../data';
import FilterBar from '../FilterBar';
import Info from '../Info';

export const dynamic = 'force-dynamic';

const card = 'flex flex-col gap-2 rounded-2xl bg-surface p-4 shadow-e1';
const H2 = 'relative text-sm font-medium text-on-surface-variant';
const note = 'text-xs text-on-surface-variant';
const R = 'text-right tabular-nums';
const usd = (x: number | null) => (x == null ? '–' : x >= 100 ? `$${Math.round(x)}` : `$${x.toFixed(2)}`);
const pct = (x: number | null, d = 0) => (x == null ? '–' : `${(x * 100).toFixed(d)}%`);
const sec = (ms: number | null) => (ms == null ? '–' : dur(ms));
const int = (x: number | null) => (x == null ? '–' : Math.round(x).toLocaleString('en-US'));

const TEXT = {
  spend: { title: 'Where the money goes', explanation: 'Estimated cost of every API request in the window, grouped by what made the call.', reading: 'Main conversation should dominate; a large side-call or compaction share is overhead worth trimming.', source: 'otel.db: api_request cost_usd, query_source' },
  turns: { title: 'What one prompt costs', explanation: 'A turn is everything one typed prompt paid for (main thread and its subagents), joined by prompt id.', reading: 'p90 is the expensive tail; a rising median means each ask does more work.', source: 'otel.db: user_prompt, api_request prompt_id' },
  concentration: { title: 'Biggest sessions', explanation: 'Sessions ranked by estimated cost, with their share of the window.', reading: 'When a few sessions hold most of the spend, per-day averages mostly describe those sessions.', source: 'otel.db: api_request by session' },
  routing: { title: 'Model and effort: cost and speed', explanation: 'Every request grouped by model and effort level: volume, cost per request, output size, latency and cache reuse.', reading: 'Compare cost per request and latency before moving work between models; small n rows swing.', source: 'otel.db: api_request' },
  tools: { title: 'Tools: failures and latency, by machine', explanation: 'Every tool call telemetry saw: how often it failed, the most common error class, and how long the call took.', reading: 'A tool that is slow or failing on one machine only points at that machine (paths, network share, shell).', source: 'otel.db: tool_result' },
  named: { title: 'Named tools, skills and slash commands', explanation: 'From the transcripts: MCP tools by server, skills and subagents by name, slash commands typed. Covers history before telemetry.', reading: 'Error rate on an MCP tool is usually the server or its limits, not the call.', source: 'tools.tsv (session-audit Stop hook and hourly run)' },
  hooks: { title: 'Hook time by event', explanation: 'Time spent in hooks, per hook event; PreToolUse and PostToolUse run on every tool call.', reading: 'p50 on PreToolUse + PostToolUse is the wait added to a typical tool call; SessionStart is paid once per session.', source: 'otel.db: hook_execution_complete' },
  subagents: { title: 'Subagents', explanation: 'Subagent runs that finished, by type and model.', reading: 'Tokens per run show what a delegation costs compared with doing it inline.', source: 'otel.db: subagent_completed' },
  friction: { title: 'Friction', explanation: 'Things that stopped or slowed work: permission-mode drops, refused tool calls, context compactions.', reading: 'auto_gate_denied in a headless run means it could not continue unattended; compactions near 167k tokens mean the context filled.', source: 'otel.db: permission_mode_changed, tool_decision, compaction' },
  output: { title: 'Output', explanation: 'Lines changed, commits and pull requests Claude Code counted in the window.', reading: 'Read next to spend: cost per committed change.', source: 'otel.db metrics: lines_of_code, commit, pull_request' },
} as const;
const I = (k: keyof typeof TEXT) => <Info title={TEXT[k].title} explanation={TEXT[k].explanation} reading={TEXT[k].reading} source={TEXT[k].source} formula="" />;
const Title = ({ k }: { k: keyof typeof TEXT }) => <h2 className={H2}>{TEXT[k].title}{I(k)}</h2>;

function Table({ head, rows, right = [] }: { head: string[]; rows: (string | number | React.ReactNode)[][]; right?: number[] }) {
  if (!rows.length) return <p className="text-sm">Nothing recorded in this window.</p>;
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead><tr className="text-left text-on-surface-variant">{head.map((h, i) => <th key={h} className={`whitespace-nowrap pr-3 font-normal ${right.includes(i) ? 'text-right' : ''}`}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, j) => <tr key={j} className="border-t border-outline/40">{r.map((c, i) => <td key={i} className={`pr-3 ${right.includes(i) ? R : ''}`}>{c}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const ctx = await loadCtx(await searchParams);
  const { q, dates, projects, models } = ctx;
  const otel = openOtel();
  const evs = otel ? filterEvents(loadEvents(otel, dates[0]!, q.today, tz()), q) : [];
  const out = otel ? outputTotals(otel, Date.parse(dates[0]!) - 86400000, Date.parse(q.today) + 2 * 86400000, q.machine) : null;
  otel?.close();
  const tools = readToolsTsv(METRICS_DIR).filter((r) => dates.includes(r.date) && (q.machine === 'all' || r.machine === q.machine) && (q.scratch || !r.scratch));
  const named = namedTools(tools);
  const spend = spendByKind(evs), t = turns(evs), conc = concentration(evs), route = routing(evs), lat = toolLatency(evs);
  const hooks = hooksByEvent(evs), subs = subagents(evs), fr = friction(evs), notes = callouts(evs, named);
  const total = spend.reduce((a, s) => a + s.cost, 0);
  const reqN = spend.reduce((a, s) => a + s.n, 0);
  const scope = `Telemetry sections honour machine, model, effort and days; the named-tools table honours machine, days and scratch. ${reqN.toLocaleString('en-US')} requests, ${usd(total)} estimated, ${dates[0]} to ${q.today}.`;

  return (
    <main className="mx-auto max-w-7xl p-4">
      <h1 className="mb-1 text-xl font-medium">Observatory · Insights</h1>
      <p className="mb-3 text-sm text-on-surface-variant">
        Totals over the whole window, where per-day lines are too thin to read. {scope}{' '}
        <a href={href(q, {}, '/')} className="text-primary underline">Overview</a>{' · '}
        <a href={href(q, {}, '/sessions')} className="text-primary underline">Sessions table</a>
      </p>
      <FilterBar q={q} base="/insights" projects={projects} models={models} />

      <section className={`${card} mb-4`}>
        <h2 className={H2}>What stands out</h2>
        {notes.length === 0 ? <p className="text-sm">Nothing crosses the thresholds in this window (at least 20 samples per claim).</p> : (
          <ul className="flex flex-col gap-1 text-sm">
            {notes.map((n) => <li key={n.text} className="flex gap-2"><span className={n.tone === 'warn' ? 'text-warn' : 'text-primary'}>{n.tone === 'warn' ? '▲' : '●'}</span><span>{n.text}</span></li>)}
          </ul>
        )}
        <p className={note}>Each line is computed from the tables below; thresholds: 10% failure, 3× latency gap between machines, 40% spend in the top tenth of sessions.</p>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className={card}>
          <Title k="spend" />
          <Table head={['Kind', 'Requests', 'Est. $', 'Share']} right={[1, 2, 3]}
            rows={spend.map((s) => [<span key="k" title={s.sources.join(', ')}>{s.kind}</span>, int(s.n), usd(s.cost), pct(s.share)])} />
          <p className={note}>Hover a kind for the raw query sources. Estimate at list price, not the bill.</p>
        </section>

        <section className={card}>
          <Title k="turns" />
          <Table head={['', 'Median', 'p90']} right={[1, 2]} rows={[
            ['Est. $ per prompt', usd(t.costP50), usd(t.costP90)],
            ['Main-thread requests per prompt', int(t.reqP50), int(t.reqP90)],
            ['Wall time per prompt', sec(t.secP50 == null ? null : t.secP50 * 1000), sec(t.secP90 == null ? null : t.secP90 * 1000)],
          ]} />
          <p className={note}>n = {t.prompts} typed prompts; most expensive single prompt {usd(t.costMax)}.</p>
        </section>

        <section className={card}>
          <Title k="concentration" />
          <Table head={['Session', 'Machine', 'Requests', 'Est. $', 'Share']} right={[2, 3, 4]}
            rows={conc.top.map((s) => [<a key="s" href={`/session/${encodeURIComponent(s.session)}`} className="font-mono text-xs text-primary underline">{s.session.slice(0, 8)}</a>, s.machine, int(s.requests), usd(s.cost), pct(s.share)])} />
          <p className={note}>n = {conc.sessions} sessions; the top tenth hold {pct(conc.top10share)} of spend.</p>
        </section>

        <section className={card}>
          <Title k="output" />
          {out ? <Table head={['Lines added', 'Lines removed', 'Commits', 'Pull requests', 'Est. $ per commit']} right={[0, 1, 2, 3, 4]}
            rows={[[int(out.added), int(out.removed), int(out.commits), int(out.prs), out.commits ? usd(total / out.commits) : '–']]} /> : <p className="text-sm">No telemetry yet.</p>}
          <p className={note}>Counted by Claude Code itself; commits made by hand are not in it.</p>
        </section>

        <section className={`${card} lg:col-span-2`}>
          <Title k="routing" />
          <Table head={['Model', 'Effort', 'Requests', 'Est. $', '$ / request', 'Output p50 tok', 'Latency p50', 'Latency p90', 'First token p50', 'Cache hit']} right={[2, 3, 4, 5, 6, 7, 8, 9]}
            rows={route.map((r) => [r.model, r.effort, int(r.n), usd(r.cost), `${(r.perReq * 100).toFixed(1)}¢`, int(r.outP50), sec(r.durP50), sec(r.durP90), sec(r.ttftP50), pct(r.cacheHit)])} />
        </section>

        <section className={`${card} lg:col-span-2`}>
          <Title k="tools" />
          <Table head={['Tool', 'Machine', 'Calls', 'Failed', 'Most common error', 'p50', 'p90', 'Result KB p50']} right={[2, 3, 5, 6, 7]}
            rows={lat.slice(0, 25).map((r) => [r.tool, r.machine, int(r.n), <span key="f" className={r.n >= 20 && r.failRate >= 0.1 ? 'font-medium text-warn' : ''}>{pct(r.failRate, 1)}</span>, r.topError ?? '–', sec(r.p50), sec(r.p90), r.kbP50 == null ? '–' : r.kbP50.toFixed(1)])} />
          <p className={note}>MCP calls show as mcp_tool here (telemetry hides the server); the table below names them.</p>
        </section>

        <section className={`${card} lg:col-span-2`}>
          <Title k="named" />
          {tools.length === 0 ? <p className="text-sm">No tools.tsv yet: it fills from the next session-audit run.</p> : (
            <Table head={['Kind', 'Name', 'Calls', 'Errors', 'Error rate', 'Denials', 'Sessions', 'MB returned']} right={[2, 3, 4, 5, 6, 7]}
              rows={named.slice(0, 40).map((r) => [r.family, r.name, int(r.calls), int(r.errors), <span key="e" className={r.calls >= 20 && r.errRate >= 0.1 ? 'font-medium text-warn' : ''}>{pct(r.errRate, 1)}</span>, int(r.denials), int(r.sessions), r.mb.toFixed(1)])} />
          )}
          <p className={note}>Top 40 by calls. Errors = tool results marked as errors; denials = refused by permissions.</p>
        </section>

        <section className={card}>
          <Title k="hooks" />
          <Table head={['Event', 'Runs', 'Total s', 'p50', 'p90', 'Max', 'Blocked', 'Errors']} right={[1, 2, 3, 4, 5, 6, 7]}
            rows={hooks.map((h) => [h.event, int(h.runs), int(h.totalS), sec(h.p50), sec(h.p90), sec(h.maxMs), int(h.blocking), int(h.errors)])} />
        </section>

        <section className={card}>
          <Title k="subagents" />
          <Table head={['Type', 'Model', 'Runs', 'Tokens p50', 'Tokens total', 'Tool uses p50', 'Time p50']} right={[2, 3, 4, 5, 6]}
            rows={subs.map((s) => [s.type, s.model, int(s.n), int(s.tokensP50), int(s.tokensTotal), int(s.toolsP50), sec(s.secP50 == null ? null : s.secP50 * 1000)])} />
        </section>

        <section className={`${card} lg:col-span-2`}>
          <Title k="friction" />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div><p className="mb-1 text-xs font-medium text-on-surface-variant">Permission-mode changes</p>
              <Table head={['From → to', 'Trigger', 'Where', 'n']} right={[3]} rows={fr.modeChanges.map((m) => [`${m.from} → ${m.to}`, m.trigger, m.terminal, int(m.n)])} /></div>
            <div><p className="mb-1 text-xs font-medium text-on-surface-variant">Refused tool calls</p>
              <Table head={['Tool', 'Refused by', 'n']} right={[2]} rows={fr.rejects.slice(0, 10).map((r) => [r.tool, r.source, int(r.n)])} /></div>
            <div><p className="mb-1 text-xs font-medium text-on-surface-variant">Compactions</p>
              <Table head={['Day', 'Trigger', 'Before', 'After', 'Took']} right={[2, 3, 4]} rows={fr.compactions.map((c) => [c.date.slice(5), c.trigger, int(c.pre), int(c.post), sec(c.sec * 1000)])} /></div>
          </div>
        </section>
      </div>
    </main>
  );
}
