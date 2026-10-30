type Row = Record<string, any>;

const NOT_SET = 'not set';

export function costTable(usage: Row[], sessions: Row[]) {
  const model = new Map<string, string>();
  for (const s of sessions) if (s.model != null && s.model !== '') model.set(String(s.session), String(s.model));
  const cells = new Map<string, { model: string; effort: string; activity: string; requests: number; cost_usd: number; out: number; sess: Set<string> }>();
  for (const u of usage) {
    const sid = String(u.session).split('/')[0];
    const m = model.get(sid);
    if (!m) continue;
    const effort = u.effort ? String(u.effort) : NOT_SET;
    const key = JSON.stringify([m, effort, u.activity]);
    let c = cells.get(key);
    if (!c) cells.set(key, (c = { model: m, effort, activity: u.activity, requests: 0, cost_usd: 0, out: 0, sess: new Set() }));
    c.requests += Number(u.requests) || 0;
    c.cost_usd += Number(u.cost_usd) || 0;
    c.out += Number(u.output) || 0;
    c.sess.add(sid);
  }
  return [...cells.values()]
    .map((c) => ({
      model: c.model, effort: c.effort, activity: c.activity,
      requests: c.requests, cost_usd: c.cost_usd,
      cost_per_request: c.requests ? c.cost_usd / c.requests : null,
      output_per_request: c.requests ? c.out / c.requests : null,
      sessions: c.sess.size,
    }))
    .sort((a, b) => b.cost_usd - a.cost_usd);
}

const attrsOf = (e: Row): Row => {
  if (typeof e.attrs === 'string') {
    try { return JSON.parse(e.attrs) ?? {}; } catch { return {}; }
  }
  return e.attrs ?? {};
};
// accept both `api_request` and `claude_code.api_request`
const nameOf = (e: Row) => String(e.name).replace(/^claude_code\./, '');

export function errorTable(events: Row[]) {
  const byReq = new Map<string, [string, string]>();
  const buckets = new Map<string, { model: string; effort: string; requests: number; tool: number; api: number; refusal: number }>();
  const bucket = (m: string, e: string) => {
    const key = m + '\u0000' + e;
    let b = buckets.get(key);
    if (!b) buckets.set(key, (b = { model: m, effort: e, requests: 0, tool: 0, api: 0, refusal: 0 }));
    return b;
  };
  const me = (a: Row): [string, string] => [a.model ? String(a.model) : 'unknown', a.effort ? String(a.effort) : NOT_SET];
  for (const e of events) {
    if (nameOf(e) !== 'api_request') continue;
    const [m, f] = me(attrsOf(e));
    if (e.request_id) byReq.set(String(e.request_id), [m, f]);
    bucket(m, f).requests++;
  }
  // request_id first, else the row's own model/effort, else unknown
  const resolve = (e: Row) => {
    const hit = e.request_id ? byReq.get(String(e.request_id)) : undefined;
    if (hit) return bucket(...hit);
    const a = attrsOf(e);
    return a.model ? bucket(...me(a)) : bucket('unknown', 'unknown');
  };
  for (const e of events) {
    const n = nameOf(e);
    if (n === 'tool_result') {
      if (String(attrsOf(e).success) === 'false') resolve(e).tool++;
    } else if (n === 'api_error') resolve(e).api++;
    else if (n === 'api_refusal') resolve(e).refusal++;
  }
  const per = (n: number, r: number) => (r ? (n / r) * 100 : null);
  return [...buckets.values()].map((b) => ({
    model: b.model, effort: b.effort, requests: b.requests,
    tool_errors_per_100: per(b.tool, b.requests),
    api_errors_per_100: per(b.api, b.requests),
    refusals_per_100: per(b.refusal, b.requests),
  }));
}
