import type { SessionRow, UsageRow } from './metrics';

export const MACHINES = ['all', 'mac', 'pc'] as const;
export const AGENTS = ['interactive', 'headless', 'all'] as const;
export const DAYS = [7, 14, 30, 90];
export const TAGS = ['CLAUDE.md', 'settings', 'plugins', 'scripts', 'other'] as const;
export const DEFAULT_OVERLAY = ['CLAUDE.md', 'settings', 'plugins', 'scripts'];
export const NOT_SET = 'not set';

export type Qs = {
  machine: 'all' | 'mac' | 'pc'; scratch: boolean; days: number; agent: 'interactive' | 'headless' | 'all';
  project: string; model: string; effort: string; from: string; to: string; overlay: string[]; today: string; custom: boolean;
};
export type RawQ = Record<string, string | string[] | undefined>;

/** Dashboard zone: TZ env, else the host zone. */
export const tz = () => process.env.TZ || Intl.DateTimeFormat().resolvedOptions().timeZone;

const DAY = 86400000;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';
const isDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s));

/** Query string -> validated filters. A valid from/to pair replaces `days`; `today` is the window's last day. */
export function parseQuery(sp: RawQ, today: string): Qs {
  const pick = <T extends string>(xs: readonly T[], v: string, d: T) => (xs as readonly string[]).includes(v) ? (v as T) : d;
  let days = DAYS.includes(Number(one(sp.days))) ? Number(one(sp.days)) : 30;
  const from = isDate(one(sp.from)) ? one(sp.from) : '';
  let to = isDate(one(sp.to)) ? one(sp.to) : '';
  let custom = false;
  if (from || to) {
    const end = to || today;
    const start = from || new Date(Date.parse(end) - (days - 1) * DAY).toISOString().slice(0, 10);
    if (start <= end) { days = Math.min(Math.round((Date.parse(end) - Date.parse(start)) / DAY) + 1, 400); to = end; custom = true; }
  }
  const ov = one(sp.overlay);
  const overlay = sp.overlay === undefined ? DEFAULT_OVERLAY : ov.split(',').filter((t) => (TAGS as readonly string[]).includes(t));
  return {
    machine: pick(MACHINES, one(sp.machine), 'all'), scratch: one(sp.scratch) === 'show', days,
    agent: pick(AGENTS, one(sp.agent), 'interactive'), project: one(sp.project).trim(), model: one(sp.model).trim(), effort: one(sp.effort).trim(),
    from: custom ? from : '', to: custom ? to : '', overlay, today: custom ? to : today, custom,
  };
}

/** Link keeping every non-default filter; `over` overrides some. */
export function href(q: Qs, over: Partial<Qs> = {}, base = '') {
  const m = { ...q, ...over };
  const p = new URLSearchParams();
  if (m.machine !== 'all') p.set('machine', m.machine);
  if (m.agent !== 'interactive') p.set('agent', m.agent);
  if (m.scratch) p.set('scratch', 'show');
  if (m.custom && m.from) { p.set('from', m.from); p.set('to', m.to); } else if (m.days !== 30) p.set('days', String(m.days));
  for (const k of ['project', 'model', 'effort'] as const) if (m[k]) p.set(k, m[k]);
  if (m.overlay.join() !== DEFAULT_OVERLAY.join()) p.set('overlay', m.overlay.join(','));
  const s = p.toString();
  return `${base}${s ? '?' + s : ''}`;
}

export const dayList = (q: Pick<Qs, 'today' | 'days'>) =>
  Array.from({ length: q.days }, (_, i) => new Date(Date.parse(q.today) - (q.days - 1 - i) * DAY).toISOString().slice(0, 10));

const baseId = (s: string) => s.split('/')[0]!;
const effortOf = (e: string | null) => e || NOT_SET;

/**
 * Narrow sessions and usage by project / model / effort. Project and model are decided on the main session row;
 * effort lives on usage rows, so a session stays only if it has usage at that effort.
 */
export function applyFilters(sessions: SessionRow[], usage: UsageRow[], f: Pick<Qs, 'project' | 'model' | 'effort'>) {
  const main = new Map(sessions.filter((s) => !s.session.includes('/')).map((s) => [s.session, s]));
  const ok = (id: string, row?: SessionRow) => {
    const m = main.get(baseId(id)) ?? row;
    return !!m && (!f.project || m.project === f.project) && (!f.model || m.model === f.model);
  };
  const uu = usage.filter((u) => ok(u.session) && (!f.effort || effortOf(u.effort) === f.effort));
  const withEffort = new Set(uu.map((u) => baseId(u.session)));
  const ss = sessions.filter((s) => ok(s.session, s) && (!f.effort || withEffort.has(baseId(s.session))));
  return { sessions: ss, usage: uu };
}
