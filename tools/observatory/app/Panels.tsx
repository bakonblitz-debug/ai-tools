import { errorTable } from '../analysis/routing';
import { startHeatmap } from '../src/heatmap';
import { coverage, filterEvents, hookTop, loadEvents, openOtel, SOURCES, toolDecisions } from '../src/otel';
import { applyFilters, href, TAGS } from '../src/query';
import { Segment } from './FilterBar';
import Spark from './Spark';
import { TAG_COLORS, type Ctx } from './data';

const card = 'flex flex-col gap-1 rounded-2xl bg-surface p-4 shadow-e1';
const SRC_COLORS = ['#1565c0', '#2e7d32', '#e08600', '#8e24aa', '#b3261c', '#6d4c41'];
const f1 = (x: number | null, d = 1) => (x == null ? '–' : x.toFixed(d));

/** Overlay legend (toggle per tag kind) and the commit list under the charts. */
export function Overlays({ ctx }: { ctx: Ctx }) {
  const { q, commits } = ctx;
  const toggle = (t: string) => href(q, { overlay: q.overlay.includes(t) ? q.overlay.filter((x) => x !== t) : [...q.overlay, t] });
  return (
    <section className={card}>
      <h2 className="text-sm font-medium text-on-surface-variant">Harness changes (vertical lines on the charts)</h2>
      <div className="flex flex-wrap gap-3 text-sm">
        {TAGS.map((t) => (
          <a key={t} href={toggle(t)} className={q.overlay.includes(t) ? 'font-medium' : 'text-on-surface-variant line-through'}>
            <span style={{ color: TAG_COLORS[t] }}>●</span> {t}
          </a>
        ))}
      </div>
      {commits.length === 0 ? <p className="text-xs text-on-surface-variant">No commits in this window (or the harness repo is not mounted).</p> : (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Date</th><th>Tags</th><th>Subject</th><th>Hash</th></tr></thead>
          <tbody>
            {commits.map((c) => (
              <tr key={c.hash}>
                <td className="whitespace-nowrap pr-3 tabular-nums">{c.date}</td>
                <td className="pr-3">{c.tags.map((t) => <span key={t} className="mr-1" style={{ color: TAG_COLORS[t] }}>{t}</span>)}</td>
                <td>{c.subject.slice(0, 80)}</td>
                <td className="font-mono text-xs">{c.hash.slice(0, 7)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function Heatmap({ ctx }: { ctx: Ctx }) {
  const grid = startHeatmap(ctx.scoped.map((s) => s.started), process.env.TZ || 'UTC');
  const max = Math.max(1, ...grid.flat());
  return (
    <section className={card}>
      <h2 className="text-sm font-medium text-on-surface-variant">When sessions start (weekday x hour)</h2>
      <div className="grid gap-px text-[10px] text-on-surface-variant" style={{ gridTemplateColumns: 'auto repeat(24, minmax(0, 1fr))' }}>
        <span />
        {Array.from({ length: 24 }, (_, h) => <span key={h} className="text-center">{h % 3 === 0 ? h : ''}</span>)}
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => (
          <div key={d} className="contents">
            <span className="pr-1">{d}</span>
            {grid[i]!.map((n, h) => <span key={h} title={`${d} ${h}:00 - ${n} sessions`} className="h-4 rounded-sm bg-primary" style={{ opacity: n ? 0.15 + 0.85 * (n / max) : 0.04 }} />)}
          </div>
        ))}
      </div>
      <p className="text-xs text-on-surface-variant">Main sessions in the current filters, local time ({process.env.TZ || 'UTC'}); darker = more starts. n = {ctx.scoped.length}.</p>
    </section>
  );
}

/** Daily stacked bars (server-rendered SVG) with grey under-covered days and commit markers. */
function Stacked({ dates, series, grey, marks }: { dates: string[]; series: [string, number[]][]; grey: boolean[]; marks: Ctx['marks'] }) {
  const W = 10, H = 100;
  const totals = dates.map((_, i) => series.reduce((a, [, v]) => a + v[i]!, 0));
  const max = Math.max(1, ...totals);
  return (
    <svg viewBox={`0 0 ${dates.length * W} ${H}`} preserveAspectRatio="none" className="h-28 w-full">
      {dates.map((d, i) => {
        let y = H;
        return (
          <g key={d}>
            {grey[i] && <rect x={i * W} y={0} width={W} height={H} fill="rgba(0,0,0,0.07)" />}
            {series.map(([name, v], k) => { const h = (v[i]! / max) * (H - 4); y -= h; return h ? <rect key={name} x={i * W + 1} y={y} width={W - 2} height={h} fill={SRC_COLORS[k % SRC_COLORS.length]}><title>{`${d} ${name}: ${v[i]}`}</title></rect> : null; })}
          </g>
        );
      })}
      {marks.map((m, j) => { const i = dates.indexOf(m.date); return i < 0 ? null : <line key={j} x1={i * W + W / 2} x2={i * W + W / 2} y1={0} y2={H} stroke={m.color} strokeWidth={2} vectorEffect="non-scaling-stroke" />; })}
    </svg>
  );
}

export function OtelPanels({ ctx }: { ctx: Ctx }) {
  const { q, dates, marks } = ctx;
  const otel = openOtel();
  const empty = (
    <section className={card}>
      <h2 className="text-sm font-medium text-on-surface-variant">Telemetry</h2>
      <p className="text-sm">No telemetry yet.</p>
    </section>
  );
  if (!otel) return empty;
  const evs = filterEvents(loadEvents(otel, dates[0]!, q.today, process.env.TZ), q);
  otel.close();
  if (evs.length === 0) return empty;
  const sessions = applyFilters(ctx.sessions, ctx.usage, { project: '', model: q.model, effort: q.effort }).sessions
    .filter((s) => dates.includes(s.date) && (q.machine === 'all' || s.machine === q.machine));
  const cov = coverage(evs, sessions, dates);
  const greyN = cov.grey.filter(Boolean).length;
  const note = 'Telemetry panels honour machine, model, effort and days; project and agent filters do not apply to them.';
  const greyNote = `Grey days have telemetry for under 90% of the transcript's requests${greyN ? ` (${greyN} in this window)` : ''}: gaps mean missing telemetry (Mac asleep, receiver down), not zero activity.`;
  const dec = toolDecisions(evs, dates);
  const errs = errorTable(evs).filter((r) => r.requests > 0).sort((a, b) => b.requests - a.requests);
  const hooks = hookTop(evs);
  const tableRows = cov.rows.slice(-14);
  return (
    <>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Telemetry coverage (OTel api_request / transcript requests)</h2>
        <Spark dates={dates} lines={[{ label: 'coverage', data: cov.combined, color: '#1565c0' }]} grey={cov.grey} marks={marks} height={140} />
        <table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Day</th><th>Machine</th><th className="text-right">OTel</th><th className="text-right">Transcript</th><th className="text-right">Coverage</th></tr></thead>
          <tbody>
            {tableRows.map((r) => (
              <tr key={r.date + r.machine} className={r.grey ? 'bg-surface-dim text-on-surface-variant' : ''}>
                <td className="tabular-nums">{r.date}</td><td>{r.machine}</td><td className="text-right tabular-nums">{r.otel}</td><td className="text-right tabular-nums">{r.transcript}</td>
                <td className="text-right tabular-nums">{r.ratio == null ? '–' : `${(r.ratio * 100).toFixed(r.ratio < 0.1 ? 1 : 0)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-on-surface-variant">{greyNote} {note}</p>
      </section>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Tool decisions by source, per day</h2>
        <Stacked dates={dates} series={SOURCES.map((s) => [s, dec[s]!])} grey={cov.grey} marks={marks} />
        <div className="flex flex-wrap gap-3 text-xs">{SOURCES.map((s, i) => <span key={s} style={{ color: SRC_COLORS[i] }}>● {s}</span>)}</div>
        <p className="text-xs text-on-surface-variant">{greyNote}</p>
      </section>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">API errors and refusals per 100 requests, by model and effort</h2>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Model</th><th>Effort</th><th className="text-right">Requests</th><th className="text-right">API errors</th><th className="text-right">Refusals</th></tr></thead>
          <tbody>
            {errs.map((r) => (
              <tr key={r.model + r.effort}><td>{r.model}</td><td>{r.effort}</td><td className="text-right tabular-nums">{r.requests}</td><td className="text-right tabular-nums">{f1(r.api_errors_per_100)}</td><td className="text-right tabular-nums">{f1(r.refusals_per_100)}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-on-surface-variant">Totals over the window, including the grey days. {note}</p>
      </section>
      <section className={card}>
        <h2 className="text-sm font-medium text-on-surface-variant">Hook time (top by total duration)</h2>
        {hooks.length === 0 ? <p className="text-sm">No hook runs recorded.</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-on-surface-variant"><th>Event</th><th>Hook (hashed)</th><th className="text-right">Runs</th><th className="text-right">Total ms</th><th className="text-right">p50</th><th className="text-right">p95</th></tr></thead>
            <tbody>
              {hooks.map((h) => (
                <tr key={h.event + h.name}><td>{h.event}</td><td className="font-mono text-xs">{h.name}</td><td className="text-right tabular-nums">{h.count}</td><td className="text-right tabular-nums">{h.total_ms.toLocaleString('en-US')}</td><td className="text-right tabular-nums">{h.p50}</td><td className="text-right tabular-nums">{h.p95}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-xs text-on-surface-variant">Per-run duration (ms) from hook_execution_complete; hook names are hashed by the receiver. {note}</p>
      </section>
    </>
  );
}
