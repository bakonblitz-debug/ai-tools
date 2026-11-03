import { computeTiles, type Tile } from '../src/metrics';
import { href, tz } from '../src/query';
import { loadCtx, type Ctx } from './data';
import FilterBar from './FilterBar';
import { Heatmap, OtelPanels, Overlays } from './Panels';
import Spark from './Spark';
import Info from './Info';
import { FORMULAS } from '../src/formulas';
import { chartOf, deltaText, fmtValue, headlineUnit, markTip, median, tips } from '../src/chart';

export const dynamic = 'force-dynamic';

const COLORS = ['#1565c0', '#e08600', '#2e7d32', '#8e24aa', '#6d4c41'];
const lineColor = (i: number) => COLORS[i % COLORS.length]!;

const fmt = (x: number | null, d = 2) => (x == null ? '–' : Math.abs(x) >= 1000 ? Math.round(x).toLocaleString('en-US') : x.toFixed(d));

function Card({ t, na, marks }: { t: Tile; na: boolean; marks: Ctx["marks"] }) {
  const tp = tips(chartOf(t), marks);
  const markTips = marks.map(markTip);
  const med = median(t.series);
  const lowN = t.ratio?.perDay.map((d) => d.lowN);
  return (
    <section className="flex flex-col gap-1 rounded-2xl bg-surface p-4 shadow-e1">
      <h2 className="relative text-sm font-medium text-on-surface-variant">{t.title}<Info title={t.title} explanation={t.explanation} reading={t.reading} source={t.source} formula={FORMULAS[t.id] ?? ''} /></h2>
      {t.byModel ? (
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Model</th><th className="text-right">Tokens</th><th className="text-right">Est. $</th></tr></thead>
          <tbody>
            {t.byModel.map((m) => (
              <tr key={m.model}><td>{m.model}</td><td className="text-right tabular-nums">{fmt(m.tokens, 0)}</td><td className="text-right tabular-nums">${m.cost.toFixed(2)}</td></tr>
            ))}
          </tbody>
        </table></div>
      ) : (
        <div className="text-3xl font-normal tabular-nums">{na ? <span className="text-lg">n/a for headless runs</span> : <>{t.effort ? '' : fmtValue(t.value, t.unit)}{!t.effort && headlineUnit(t.unit) && <span className="ml-1 text-sm text-on-surface-variant">{headlineUnit(t.unit)}</span>}{!t.effort && t.id !== 'models' && <span className="ml-2 text-xs text-on-surface-variant">{deltaText(t.value, t.prev)}</span>}</>}</div>
      )}
      {t.effort && (
        <>
          <Spark dates={t.dates} unit="share" yRange={[0, 1]} tips={tp} markTips={markTips} marks={marks} lines={Object.entries(t.effort).map(([label, data], i) => ({ label, data, color: lineColor(i) }))} />
          <div className="flex flex-wrap gap-3 text-xs">
            {Object.keys(t.effort).map((e, i) => <span key={e} style={{ color: lineColor(i) }}>● {e}</span>)}
          </div>
        </>
      )}
      {!t.byModel && !t.effort && (
        <Spark marks={marks} unit={t.unit} tips={tp} markTips={markTips}
          reference={med == null ? undefined : { value: med, label: `median of days ${fmtValue(med, t.unit)}` }}
          dates={t.dates}
          lines={[{ label: t.title, data: t.series, color: lineColor(0) }]}
          grey={lowN}
          band={t.ratio && { lo: t.ratio.iqr.map((q, i) => (q && !lowN![i] ? q[0] : null)), hi: t.ratio.iqr.map((q, i) => (q && !lowN![i] ? q[1] : null)) }}
        />
      )}
      <p className="text-xs text-on-surface-variant">
        n = {t.n} {t.effort ? 'sessions with usage' : 'sessions'}
        {t.ratio?.lastLargestShare != null && ` · largest session ${Math.round(t.ratio.lastLargestShare * 100)}% of the day`}
        {t.ratio && ' · shaded band = middle half of sessions'}
      </p>
    </section>
  );
}

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const ctx = await loadCtx(await searchParams);
  const { q, meta, sessions, f, projects, models } = ctx;
  const mine = sessions.filter((r) => q.machine === 'all' || r.machine === q.machine);
  const kindN = (ks: string[]) => mine.filter((r) => ks.includes(r.agent_kind)).length;
  const split = `${q.machine === 'all' ? 'both machines' : q.machine}: interactive ${kindN(['interactive', 'subagent'])} · headless ${kindN(['headless', 'hook'])} · unknown ${kindN(['unknown'])} · no API calls ${kindN(['no-api'])}`;
  const tiles = computeTiles(f.sessions, f.usage, { machine: q.machine, scratch: q.scratch, days: q.days, agent: q.agent, today: q.today }, meta?.pricesAsOf ?? null);

  return (
    <main className="mx-auto max-w-7xl p-4">
      <h1 className="mb-1 text-xl font-medium">Observatory</h1>
      <p className="mb-3 text-sm text-on-surface-variant">
        Covers Mac {meta?.rows['sessions.mac'] ?? 0} · PC {meta?.rows['sessions.pc'] ?? 0} sessions ({split}) · loaded {meta ? new Date(meta.loadedAt).toLocaleString('en-CA', { timeZone: tz() }) : 'never'} · {(meta?.ragged.mac ?? 0) + (meta?.ragged.pc ?? 0)} ragged rows · {(meta?.preEffort?.mac ?? 0) + (meta?.preEffort?.pc ?? 0)} pre-effort rows
        {meta?.refused && <span className="ml-1 font-medium text-warn"> · refused: {meta.refused}</span>}
        {' · '}<a href={href(q, {}, '/sessions')} className="text-primary underline">Sessions table</a>
      </p>
      <FilterBar q={q} base="" projects={projects} models={models} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t) => <Card key={t.id} t={t} marks={ctx.marks} na={t.id === 'interruptions' && q.agent === 'headless'} />)}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Overlays ctx={ctx as Ctx} />
        <Heatmap ctx={ctx as Ctx} />
        <OtelPanels ctx={ctx as Ctx} />
      </div>
    </main>
  );
}
