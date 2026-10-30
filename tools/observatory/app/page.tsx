import { ensureFresh, openDb, readMeta } from '../src/loader';
import { computeTiles, type SessionRow, type Tile, type UsageRow } from '../src/metrics';
import Spark from './Spark';

export const dynamic = 'force-dynamic';

const COLORS = ['#1565c0', '#e08600', '#2e7d32', '#8e24aa', '#6d4c41'];
const lineColor = (i: number) => COLORS[i % COLORS.length]!;

const METRICS_DIR = process.env.METRICS_DIR_IN_CONTAINER ?? '/data/metrics';
let db: ReturnType<typeof openDb> | undefined;

type Q = { machine?: string; scratch?: string; days?: string; agent?: string };
const AGENTS = ['interactive', 'headless', 'all'] as const;
type Qs = { machine: string; scratch: boolean; days: number; agent: string };
const MACHINES = ['all', 'mac', 'pc'] as const;
const DAYS = [7, 14, 30, 90];

function href(q: Qs, over: Partial<Qs>) {
  const m = { ...q, ...over };
  const p = new URLSearchParams({ machine: m.machine, days: String(m.days), agent: m.agent });
  if (m.scratch) p.set('scratch', 'show');
  return `?${p}`;
}

function Segment({ label, items }: { label: string; items: { text: string; href: string; on: boolean }[] }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-on-surface-variant">{label}</span>
      <div className="flex overflow-hidden rounded-full border border-outline">
        {items.map((i) => (
          <a key={i.text} href={i.href} className={`px-3 py-1 ${i.on ? 'bg-primary-container font-medium text-primary-dark' : 'hover:bg-surface-dim'}`}>{i.text}</a>
        ))}
      </div>
    </div>
  );
}

const fmt = (x: number | null, d = 2) => (x == null ? '–' : Math.abs(x) >= 1000 ? Math.round(x).toLocaleString('en-US') : x.toFixed(d));

function Card({ t, na }: { t: Tile; na: boolean }) {
  const lowN = t.ratio?.perDay.map((d) => d.lowN);
  return (
    <section className="flex flex-col gap-1 rounded-2xl bg-surface p-4 shadow-e1">
      <h2 className="text-sm font-medium text-on-surface-variant">{t.title}</h2>
      {t.byModel ? (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-on-surface-variant"><th>Model</th><th className="text-right">Tokens</th><th className="text-right">Est. $</th></tr></thead>
          <tbody>
            {t.byModel.map((m) => (
              <tr key={m.model}><td>{m.model}</td><td className="text-right tabular-nums">{fmt(m.tokens, 0)}</td><td className="text-right tabular-nums">${m.cost.toFixed(2)}</td></tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="text-3xl font-normal tabular-nums">{na ? <span className="text-lg">n/a for headless runs</span> : <>{t.effort ? '' : fmt(t.value)}<span className="ml-1 text-sm text-on-surface-variant">{t.effort ? '' : t.unit}</span></>}</div>
      )}
      {t.effort && (
        <>
          <Spark dates={t.dates} lines={Object.entries(t.effort).map(([label, data], i) => ({ label, data, color: lineColor(i) }))} />
          <div className="flex flex-wrap gap-3 text-xs">
            {Object.keys(t.effort).map((e, i) => <span key={e} style={{ color: lineColor(i) }}>● {e}</span>)}
          </div>
        </>
      )}
      {!t.byModel && !t.effort && (
        <Spark
          dates={t.dates}
          lines={[{ label: t.title, data: t.series, color: lineColor(0) }]}
          grey={lowN}
          band={t.ratio && { lo: t.ratio.iqr.map((q, i) => (q && !lowN![i] ? q[0] : null)), hi: t.ratio.iqr.map((q, i) => (q && !lowN![i] ? q[1] : null)) }}
        />
      )}
      <p className="text-xs text-on-surface-variant">{t.explanation}</p>
      <p className="text-xs text-on-surface-variant">
        n = {t.n} {t.effort ? 'sessions with usage' : 'sessions'}
        {t.ratio?.lastLargestShare != null && ` · largest session ${Math.round(t.ratio.lastLargestShare * 100)}% of the day`}
        {t.ratio && ' · shaded band = middle half of sessions'}
      </p>
    </section>
  );
}

export default async function Page({ searchParams }: { searchParams: Promise<Q> }) {
  const sp = await searchParams;
  const machine = (MACHINES as readonly string[]).includes(sp.machine ?? '') ? (sp.machine as (typeof MACHINES)[number]) : 'all';
  const scratch = sp.scratch === 'show';
  const days = DAYS.includes(Number(sp.days)) ? Number(sp.days) : 30;
  const agent = (AGENTS as readonly string[]).includes(sp.agent ?? '') ? (sp.agent as (typeof AGENTS)[number]) : 'interactive';
  const q = { machine, scratch, days, agent };

  db ??= openDb();
  ensureFresh(db, METRICS_DIR, process.env);
  const meta = readMeta(db);
  const sessions = db.prepare('SELECT * FROM sessions').all() as SessionRow[];
  const usage = db.prepare('SELECT * FROM usage').all() as UsageRow[];
  const today = new Date().toLocaleDateString('en-CA', { timeZone: process.env.TZ });
  const mine = sessions.filter((r) => machine === 'all' || r.machine === machine);
  const kindN = (ks: string[]) => mine.filter((r) => ks.includes(r.agent_kind)).length;
  const split = `${machine === 'all' ? 'both machines' : machine}: interactive ${kindN(['interactive', 'subagent'])} · headless ${kindN(['headless', 'hook'])} · unknown ${kindN(['unknown'])} · no API calls ${kindN(['no-api'])}`;
  const tiles = computeTiles(sessions, usage, { machine, scratch, days, agent, today }, meta?.pricesAsOf ?? null);

  return (
    <main className="mx-auto max-w-7xl p-4">
      <h1 className="mb-1 text-xl font-medium">Observatory</h1>
      <p className="mb-3 text-sm text-on-surface-variant">
        Covers Mac {meta?.rows['sessions.mac'] ?? 0} · PC {meta?.rows['sessions.pc'] ?? 0} sessions ({split}) · loaded {meta ? new Date(meta.loadedAt).toLocaleString('en-CA', { timeZone: process.env.TZ }) : 'never'} · {(meta?.ragged.mac ?? 0) + (meta?.ragged.pc ?? 0)} ragged rows · {(meta?.preEffort?.mac ?? 0) + (meta?.preEffort?.pc ?? 0)} pre-effort rows
        {meta?.refused && <span className="ml-1 font-medium text-warn"> · refused: {meta.refused}</span>}
      </p>
      <div className="mb-4 flex flex-wrap gap-x-6 gap-y-2">
        <Segment label="Machine" items={MACHINES.map((m) => ({ text: m, href: href(q, { machine: m }), on: m === machine }))} />
        <Segment label="Agent" items={AGENTS.map((a) => ({ text: a, href: href(q, { agent: a }), on: a === agent }))} />
        <Segment label="Days" items={DAYS.map((d) => ({ text: String(d), href: href(q, { days: d }), on: d === days }))} />
        <Segment label="Scratch" items={[{ text: 'hidden', href: href(q, { scratch: false }), on: !scratch }, { text: 'shown', href: href(q, { scratch: true }), on: scratch }]} />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t) => <Card key={t.id} t={t} na={t.id === 'interruptions' && agent === 'headless'} />)}
      </div>
    </main>
  );
}
