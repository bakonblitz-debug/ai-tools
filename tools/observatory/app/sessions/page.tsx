import { href } from '../../src/query';
import { loadCtx } from '../data';
import FilterBar from '../FilterBar';

export const dynamic = 'force-dynamic';

const PER = 50;
const v = (x: number | null | undefined) => x ?? 0;
const SORTS = {
  date: ['Date', (r: Row) => r.started ?? r.date],
  tokens: ['Tokens', (r: Row) => r.tokens],
  cost: ['Cost', (r: Row) => r.cost],
  active: ['Active h', (r: Row) => v(r.active_s)],
  errors: ['Tool errors', (r: Row) => v(r.tool_errors)],
} as const;
type Row = Awaited<ReturnType<typeof loadCtx>>['scoped'][number] & { tokens: number; cost: number };

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const ctx = await loadCtx(sp);
  const { q } = ctx;
  const one = (k: string) => { const x = sp[k]; return (Array.isArray(x) ? x[0] : x) ?? ''; };
  const sort = (one('sort') in SORTS ? one('sort') : 'date') as keyof typeof SORTS;
  const cost = new Map<string, number>();
  for (const u of ctx.f.usage) cost.set(u.session, (cost.get(u.session) ?? 0) + v(u.cost_usd));
  const rows: Row[] = ctx.scoped.map((s) => ({ ...s, tokens: v(s.tokens_in) + v(s.tokens_out) + v(s.cache_read) + v(s.cache_create), cost: cost.get(s.session) ?? 0 }));
  const key = SORTS[sort][1];
  rows.sort((a, b) => { const x = key(a), y = key(b); return x < y ? 1 : x > y ? -1 : 0; });
  const pages = Math.max(1, Math.ceil(rows.length / PER));
  const page = Math.min(Math.max(Number(one('page')) || 1, 1), pages);
  const base = href(q, {}, '/sessions');
  const link = (extra: Record<string, string>) => `${base}${base.includes('?') ? '&' : '?'}${new URLSearchParams(extra)}`;

  return (
    <main className="mx-auto max-w-7xl p-4">
      <h1 className="mb-1 text-xl font-medium"><a href={href(q)} className="text-primary">Observatory</a> / Sessions</h1>
      <FilterBar q={q} base="/sessions" projects={ctx.projects} models={ctx.models} />
      <section className="rounded-2xl bg-surface p-4 shadow-e1">
        <p className="mb-2 text-sm text-on-surface-variant">{rows.length} main sessions in the current filters, sorted by {SORTS[sort][0].toLowerCase()} (largest first); page {page} of {pages}.</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-on-surface-variant">
              <th>Session</th><th>Machine</th><th>Project</th><th>Model</th>
              {(Object.keys(SORTS) as (keyof typeof SORTS)[]).map((k) => (
                <th key={k} className="text-right"><a href={link({ sort: k })} className={k === sort ? 'font-medium text-primary-dark' : 'hover:underline'}>{SORTS[k][0]}{k === sort ? ' ▼' : ''}</a></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice((page - 1) * PER, page * PER).map((r) => (
              <tr key={r.session} className="border-t border-outline">
                <td className="font-mono text-xs"><a href={`/session/${encodeURIComponent(r.session)}`} className="text-primary underline">{r.session.slice(0, 8)}</a></td>
                <td>{r.machine}</td><td>{r.project}</td><td>{r.model}</td>
                <td className="whitespace-nowrap text-right tabular-nums">{r.started?.replace('T', ' ').slice(0, 16) ?? r.date}</td>
                <td className="text-right tabular-nums">{r.tokens.toLocaleString('en-US')}</td>
                <td className="text-right tabular-nums">${r.cost.toFixed(2)}</td>
                <td className="text-right tabular-nums">{(v(r.active_s) / 3600).toFixed(2)}</td>
                <td className="text-right tabular-nums">{v(r.tool_errors)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 flex gap-4 text-sm">
          {page > 1 && <a href={link({ sort, page: String(page - 1) })} className="text-primary underline">Previous</a>}
          {page < pages && <a href={link({ sort, page: String(page + 1) })} className="text-primary underline">Next</a>}
        </p>
        <p className="mt-1 text-xs text-on-surface-variant">Date is the session start (UTC as logged). Cost is an estimate from list prices.</p>
      </section>
    </main>
  );
}
