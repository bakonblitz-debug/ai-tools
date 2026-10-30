import { AGENTS, DAYS, MACHINES, href, type Qs } from '../src/query';

export function Segment({ label, items }: { label: string; items: { text: string; href: string; on: boolean }[] }) {
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

const field = 'rounded-lg border border-outline bg-surface px-2 py-1 text-sm';

/** Segment links for machine/agent/days/scratch, plus a GET form for project, model, effort and a date window. No client JS. */
export default function FilterBar({ q, base, projects, models }: { q: Qs; base: string; projects: string[]; models: string[] }) {
  const h = (over: Partial<Qs>) => href(q, over, base);
  const active = !!(q.project || q.model || q.effort || q.custom);
  return (
    <div className="mb-4 flex flex-col gap-2">
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <Segment label="Machine" items={MACHINES.map((m) => ({ text: m, href: h({ machine: m }), on: m === q.machine }))} />
        <Segment label="Agent" items={AGENTS.map((a) => ({ text: a, href: h({ agent: a }), on: a === q.agent }))} />
        <Segment label="Days" items={DAYS.map((d) => ({ text: String(d), href: h({ days: d, custom: false }), on: !q.custom && d === q.days }))} />
        <Segment label="Scratch" items={[{ text: 'hidden', href: h({ scratch: false }), on: !q.scratch }, { text: 'shown', href: h({ scratch: true }), on: q.scratch }]} />
      </div>
      <form method="get" action={base || undefined} className="flex flex-wrap items-center gap-2 text-sm">
        {q.machine !== 'all' && <input type="hidden" name="machine" value={q.machine} />}
        {q.agent !== 'interactive' && <input type="hidden" name="agent" value={q.agent} />}
        {q.scratch && <input type="hidden" name="scratch" value="show" />}
        {!q.custom && q.days !== 30 && <input type="hidden" name="days" value={q.days} />}
        <input type="hidden" name="overlay" value={q.overlay.join(',')} />
        <label className="flex items-center gap-1 text-on-surface-variant">Project <input name="project" list="projects" defaultValue={q.project} className={field} /></label>
        <datalist id="projects">{projects.map((p) => <option key={p} value={p} />)}</datalist>
        <label className="flex items-center gap-1 text-on-surface-variant">Model <input name="model" list="models" defaultValue={q.model} className={field} /></label>
        <datalist id="models">{models.map((m) => <option key={m} value={m} />)}</datalist>
        <label className="flex items-center gap-1 text-on-surface-variant">Effort
          <select name="effort" defaultValue={q.effort} className={field}>
            {['', 'low', 'medium', 'high', 'xhigh', 'max', 'not set'].map((e) => <option key={e} value={e}>{e || 'any'}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-on-surface-variant">From <input type="date" name="from" defaultValue={q.from} className={field} /></label>
        <label className="flex items-center gap-1 text-on-surface-variant">To <input type="date" name="to" defaultValue={q.to} className={field} /></label>
        <button type="submit" className="rounded-full bg-primary px-4 py-1 text-on-primary">Apply</button>
        {active && <a href={href({ ...q, project: '', model: '', effort: '', from: '', to: '', custom: false, days: q.custom ? 30 : q.days }, {}, base) || base || '?'} className="text-primary underline">clear filters</a>}
      </form>
    </div>
  );
}
