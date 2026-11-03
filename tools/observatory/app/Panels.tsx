import { errorTable } from '../analysis/routing';
import { startHeatmap } from '../src/heatmap';
import { coverage, filterEvents, hookTop, loadEvents, openOtel, SOURCES, toolDecisions } from '../src/otel';
import { applyFilters, href, TAGS, tz } from '../src/query';
import { Segment } from './FilterBar';
import Info from './Info';
import Spark from './Spark';
import { FORMULAS, PANELS } from '../src/formulas';
import { markTip, monthDay, stackTip, tipAnchor, tips, whenOf } from '../src/chart';
import { TAG_COLORS, type Ctx } from './data';

const card = 'flex flex-col gap-1 rounded-2xl bg-surface p-4 shadow-e1';
const SRC_COLORS = ['#1565c0', '#2e7d32', '#e08600', '#8e24aa', '#b3261c', '#6d4c41'];
const H2 = 'relative text-sm font-medium text-on-surface-variant';
const I = (id: keyof typeof PANELS & string) => <Info title={PANELS[id]!.title} explanation={PANELS[id]!.explanation} reading={PANELS[id]!.reading} source={PANELS[id]!.source} formula={FORMULAS[id]!} />;
const f1 = (x: number | null, d = 1) => (x == null ? '–' : x.toFixed(d));

/** Overlay legend (toggle per tag kind) and the commit list under the charts. */
export function Overlays({ ctx }: { ctx: Ctx }) {
  const { q, commits } = ctx;
  const toggle = (t: string) => href(q, { overlay: q.overlay.includes(t) ? q.overlay.filter((x) => x !== t) : [...q.overlay, t] });
  return (
    <section className={card}>
      <h2 className={H2}>Harness changes (vertical lines on the charts){I('overlays')}</h2>
      <div className="flex flex-wrap gap-3 text-sm">
        {TAGS.map((t) => (
          <a key={t} href={toggle(t)} className={q.overlay.includes(t) ? 'font-medium' : 'text-on-surface-variant line-through'}>
            <span style={{ color: TAG_COLORS[t] }}>●</span> {t}
          </a>
        ))}
      </div>
      {commits.length === 0 ? <p className="text-xs text-on-surface-variant">No commits in this window (or the harness repo is not mounted).</p> : (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>When</th><th>Tags</th><th>Subject</th><th>Hash</th></tr></thead>
          <tbody>
            {commits.map((c) => (
              <tr key={c.hash}>
                <td className="whitespace-nowrap pr-3 tabular-nums">{whenOf(c.at)}</td>
                <td className="pr-3">{c.tags.map((t) => <span key={t} className="mr-1" style={{ color: TAG_COLORS[t] }}>{t}</span>)}</td>
                <td>{c.subject.slice(0, 80)}</td>
                <td className="font-mono text-xs">{c.hash.slice(0, 7)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </section>
  );
}

export function Heatmap({ ctx }: { ctx: Ctx }) {
  const grid = startHeatmap(ctx.scoped.map((s) => s.started), tz());
  const max = Math.max(1, ...grid.flat());
  return (
    <section className={card}>
      <h2 className={H2}>When sessions start (weekday x hour){I('heatmap')}</h2>
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
      <p className="text-xs text-on-surface-variant">Main sessions in the current filters, local time ({tz()}); darker = more starts. n = {ctx.scoped.length}.</p>
    </section>
  );
}

/** Daily stacked bars as HTML columns: Y scale, grey under-covered days, a commit bar per day, CSS tooltips on hover or focus. */
function Stacked({ dates, series, grey, marks }: { dates: string[]; series: [string, number[]][]; grey: boolean[]; marks: Ctx['marks'] }) {
  const n = dates.length;
  const totals = dates.map((_, i) => series.reduce((a, [, v]) => a + v[i]!, 0));
  const max = Math.max(1, ...totals);
  const half = max < 10 ? (max / 2).toFixed(1) : String(Math.round(max / 2));
  const every = Math.ceil(n / 6);
  const align = { left: 'left-0', center: 'left-1/2 -translate-x-1/2', right: 'right-0' };
  return (
    <div className="flex flex-col gap-1 text-[10px] text-on-surface-variant">
      <div className="flex gap-2">
        <div className="relative h-28 w-8 shrink-0 text-right tabular-nums">
          <span className="absolute top-0 right-0 -translate-y-1/2">{max}</span>
          <span className="absolute top-1/2 right-0 -translate-y-1/2">{half}</span>
          <span className="absolute bottom-0 right-0 translate-y-1/2">0</span>
        </div>
        <div className="relative h-28 flex-1">
          <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
            <div className="border-t border-outline/60" />
            <div className="border-t border-outline/60" />
            <div className="border-t border-outline/60" />
          </div>
          <div className="relative flex h-full gap-px">
            {dates.map((d, i) => {
              const mark = marks.find((m) => m.date === d);
              const lines = stackTip(i, dates, series, marks);
              return (
                <div key={d} tabIndex={0} role="img" aria-label={lines.join(', ')} className={`group relative flex h-full flex-1 flex-col-reverse focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${grey[i] ? 'bg-[rgba(0,0,0,0.07)]' : ''}`}>
                  {series.map(([name, v], k) => v[i] ? <div key={name} style={{ height: `${(v[i]! / max) * 100}%`, backgroundColor: SRC_COLORS[k % SRC_COLORS.length] }} /> : null)}
                  {mark && <div className="absolute inset-x-0 top-0 h-0.5" style={{ backgroundColor: mark.color }} />}
                  <div className={`pointer-events-none absolute bottom-full z-10 hidden w-max max-w-[min(22rem,50vw)] whitespace-pre-line rounded bg-surface px-2 py-1 text-xs text-on-surface shadow-e2 group-hover:block group-focus:block ${align[tipAnchor(i, n)]}`}>{lines.join('\n')}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="flex gap-2">
        <span className="w-8 shrink-0" />
        <div className="flex flex-1 gap-px">
          {dates.map((d, i) => <span key={d} className="min-w-0 flex-1 overflow-visible whitespace-nowrap">{i % every === 0 ? monthDay(d) : ''}</span>)}
        </div>
      </div>
    </div>
  );
}

export function OtelPanels({ ctx }: { ctx: Ctx }) {
  const { q, dates, marks } = ctx;
  const otel = openOtel();
  const empty = (
    <section className={card}>
      <h2 className="relative text-sm font-medium text-on-surface-variant">Telemetry</h2>
      <p className="text-sm">No telemetry yet.</p>
    </section>
  );
  if (!otel) return empty;
  const evs = filterEvents(loadEvents(otel, dates[0]!, q.today, tz()), q);
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
        <h2 className={H2}>Telemetry coverage (OTel api_request / transcript requests){I('coverage')}</h2>
        <Spark dates={dates} unit="share" tips={tips({ dates, unit: 'share', lines: [{ label: 'coverage', data: cov.combined }] }, marks)} lines={[{ label: 'coverage', data: cov.combined, color: '#1565c0' }]} grey={cov.grey} marks={marks} markTips={marks.map(markTip)} height={160} />
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Day</th><th>Machine</th><th className="text-right">OTel</th><th className="text-right">Transcript</th><th className="text-right">Coverage</th></tr></thead>
          <tbody>
            {tableRows.map((r) => (
              <tr key={r.date + r.machine} className={r.grey ? 'bg-surface-dim text-on-surface-variant' : ''}>
                <td className="tabular-nums">{r.date}</td><td>{r.machine}</td><td className="text-right tabular-nums">{r.otel}</td><td className="text-right tabular-nums">{r.transcript}</td>
                <td className="text-right tabular-nums">{r.ratio == null ? '–' : `${(r.ratio * 100).toFixed(r.ratio < 0.1 ? 1 : 0)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
        <p className="text-xs text-on-surface-variant">{greyNote} {note}</p>
      </section>
      <section className={card}>
        <h2 className={H2}>Tool decisions by source, per day{I('toolDecisions')}</h2>
        <Stacked dates={dates} series={SOURCES.map((s) => [s, dec[s]!])} grey={cov.grey} marks={marks} />
        <div className="flex flex-wrap gap-3 text-xs">{SOURCES.map((s, i) => <span key={s} style={{ color: SRC_COLORS[i] }}>● {s}</span>)}</div>
        <p className="text-xs text-on-surface-variant">{greyNote}</p>
      </section>
      <section className={card}>
        <h2 className={H2}>API errors and refusals per 100 requests, by model and effort{I('apiErrors')}</h2>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Model</th><th>Effort</th><th className="text-right">Requests</th><th className="text-right">API errors</th><th className="text-right">Refusals</th></tr></thead>
          <tbody>
            {errs.map((r) => (
              <tr key={r.model + r.effort}><td>{r.model}</td><td>{r.effort}</td><td className="text-right tabular-nums">{r.requests}</td><td className="text-right tabular-nums">{f1(r.api_errors_per_100)}</td><td className="text-right tabular-nums">{f1(r.refusals_per_100)}</td></tr>
            ))}
          </tbody>
        </table></div>
        <p className="text-xs text-on-surface-variant">Totals over the window, including the grey days. {note}</p>
      </section>
      <section className={card}>
        <h2 className={H2}>Hook time (top by total duration){I('hooks')}</h2>
        {hooks.length === 0 ? <p className="text-sm">No hook runs recorded.</p> : (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="text-left text-on-surface-variant"><th>Event</th><th>Hook (hashed)</th><th className="text-right">Runs</th><th className="text-right">Total ms</th><th className="text-right">p50</th><th className="text-right">p95</th></tr></thead>
            <tbody>
              {hooks.map((h) => (
                <tr key={h.event + h.name}><td>{h.event}</td><td className="font-mono text-xs">{h.name}</td><td className="text-right tabular-nums">{h.count}</td><td className="text-right tabular-nums">{h.total_ms.toLocaleString('en-US')}</td><td className="text-right tabular-nums">{h.p50}</td><td className="text-right tabular-nums">{h.p95}</td></tr>
              ))}
            </tbody>
          </table></div>
        )}
        <p className="text-xs text-on-surface-variant">Per-run duration (ms) from hook_execution_complete; hook names are hashed by the receiver. {note}</p>
      </section>
    </>
  );
}
