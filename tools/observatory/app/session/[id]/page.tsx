import { ensureFresh, openDb } from '../../../src/loader';
import type { SessionRow, UsageRow } from '../../../src/metrics';
import { loadSessionEvents, openOtel, waterfall } from '../../../src/otel';
import { METRICS_DIR } from '../../data';

export const dynamic = 'force-dynamic';

const nf = (x: number | null | undefined) => (x == null ? '–' : x.toLocaleString('en-US'));
const th = 'text-left text-on-surface-variant';
const card = 'flex flex-col gap-2 rounded-2xl bg-surface p-4 shadow-e1';
let db: ReturnType<typeof openDb> | undefined;

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const id = decodeURIComponent((await params).id);
  db ??= openDb();
  ensureFresh(db, METRICS_DIR, process.env);
  const s = db.prepare('SELECT * FROM sessions WHERE session = ?').get(id) as (SessionRow & Record<string, any>) | undefined;
  const usage = db.prepare('SELECT * FROM usage WHERE session = ?').all(id) as (UsageRow & { activity: string; output: number | null })[];
  const subs = db.prepare('SELECT * FROM sessions WHERE substr(session, 1, ?) = ?').all(id.length + 1, id + '/') as (SessionRow & Record<string, any>)[];
  const cells = new Map<string, { activity: string; effort: string; requests: number; cost: number; output: number }>();
  for (const u of usage) {
    const k = u.activity + '|' + (u.effort || 'not set');
    const c = cells.get(k) ?? { activity: u.activity, effort: u.effort || 'not set', requests: 0, cost: 0, output: 0 };
    c.requests += u.requests ?? 0; c.cost += u.cost_usd ?? 0; c.output += u.output ?? 0;
    cells.set(k, c);
  }
  const otel = openOtel();
  const wf = otel ? waterfall(loadSessionEvents(otel, id, process.env.TZ)) : null;
  otel?.close();
  const maxDur = Math.max(1, ...(wf?.rows.map((r) => r.duration_ms ?? 0) ?? []));

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-4">
      <h1 className="text-xl font-medium"><a href="/" className="text-primary">Observatory</a> / <a href="/sessions" className="text-primary">Sessions</a> / <span className="font-mono text-base">{id}</span></h1>
      {!s ? <section className={card}><p className="text-sm">No session with this id in the loaded metrics.</p></section> : (
        <section className={card}>
          <h2 className="text-sm font-medium text-on-surface-variant">Session</h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
            {([
              ['Machine', s.machine], ['Project', s.project], ['Model', s.model], ['Kind', s.agent_kind],
              ['Started', s.started], ['Ended', s.ended], ['Duration s', nf(s.duration_s)], ['Active s', nf(s.active_s)],
              ['Assistant msgs', nf(s.assistant_msgs)], ['Tool errors', nf(s.tool_errors)], ['Denials', nf(s.denials)], ['Interruptions', nf(s.interruptions)],
              ['Tokens in', nf(s.tokens_in)], ['Tokens out', nf(s.tokens_out)], ['Cache read', nf(s.cache_read)], ['Cache create', nf(s.cache_create)],
            ] as [string, unknown][]).map(([k, val]) => <div key={k}><dt className="text-xs text-on-surface-variant">{k}</dt><dd className="tabular-nums">{String(val ?? '–')}</dd></div>)}
          </dl>
        </section>
      )}
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Usage by activity and effort</h2>
        <table className="w-full text-sm">
          <thead><tr className={th}><th>Activity</th><th>Effort</th><th className="text-right">Requests</th><th className="text-right">Output tokens</th><th className="text-right">Est. $</th></tr></thead>
          <tbody>{[...cells.values()].map((c) => <tr key={c.activity + c.effort}><td>{c.activity}</td><td>{c.effort}</td><td className="text-right tabular-nums">{nf(c.requests)}</td><td className="text-right tabular-nums">{nf(c.output)}</td><td className="text-right tabular-nums">${c.cost.toFixed(2)}</td></tr>)}</tbody>
        </table>
        {cells.size === 0 && <p className="text-sm">No usage rows.</p>}
      </section>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Subagents ({subs.length})</h2>
        {subs.length > 0 && (
          <table className="w-full text-sm">
            <thead><tr className={th}><th>Id</th><th>Model</th><th className="text-right">Requests</th><th className="text-right">Active s</th><th className="text-right">Tool errors</th></tr></thead>
            <tbody>{subs.map((r) => <tr key={r.session}><td className="font-mono text-xs">{r.session.slice(id.length + 1)}</td><td>{r.model}</td><td className="text-right tabular-nums">{nf(r.assistant_msgs)}</td><td className="text-right tabular-nums">{nf(r.active_s)}</td><td className="text-right tabular-nums">{nf(r.tool_errors)}</td></tr>)}</tbody>
          </table>
        )}
      </section>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Request waterfall</h2>
        {!wf || wf.rows.length === 0 ? (
          <p className="text-sm">no telemetry for this session (it ran before 2026-10-30 or the receiver was unreachable)</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className={th}><th>+s</th><th>Model</th><th>Effort</th><th className="text-right">In</th><th className="text-right">Out</th><th className="text-right">Cache r/w</th><th className="w-48">Duration ms</th><th className="text-right">TTFT</th><th className="text-right">$</th><th>Source</th><th>Tools and errors</th></tr></thead>
            <tbody>
              {wf.rows.map((r) => (
                <tr key={r.ts + r.model} className="border-t border-outline align-top">
                  <td className="tabular-nums">{(r.offset_ms / 1000).toFixed(1)}</td><td>{r.model}</td><td>{r.effort}</td>
                  <td className="text-right tabular-nums">{nf(r.input)}</td><td className="text-right tabular-nums">{nf(r.output)}</td><td className="text-right tabular-nums">{nf(r.cache_read)}/{nf(r.cache_create)}</td>
                  <td><div className="flex items-center gap-1"><div className="h-3 rounded-sm bg-primary" style={{ width: `${((r.duration_ms ?? 0) / maxDur) * 100}%` }} /><span className="tabular-nums">{nf(r.duration_ms)}</span></div></td>
                  <td className="text-right tabular-nums">{nf(r.ttft_ms)}</td><td className="text-right tabular-nums">{r.cost == null ? '–' : r.cost.toFixed(4)}</td><td>{r.query_source}</td>
                  <td className="text-xs">
                    {r.tools.map((t, i) => <div key={i} className={t.success ? '' : 'text-warn'}>{t.tool} {t.success ? 'ok' : 'failed'} {nf(t.duration_ms)} ms</div>)}
                    {r.errors.map((e, i) => <div key={i} className="text-warn">api_error {e.status}</div>)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {wf && wf.orphanErrors.length > 0 && <p className="text-xs text-warn">{wf.orphanErrors.length} api_error events not tied to a request above.</p>}
      </section>
    </main>
  );
}
