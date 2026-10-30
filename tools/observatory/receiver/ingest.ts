import { createHash } from 'node:crypto';

export type Row = {
  kind: 'event' | 'metric';
  name: string;
  ts: number; // epoch ms
  session_id: string | null;
  prompt_id: string | null;
  request_id: string | null;
  machine: string | null;
  value: number | null;
  attrs: string; // JSON
};

type KV = { key: string; value?: Record<string, unknown> };

const DROP = new Set([
  'user.email', 'user.id', 'user.account_uuid', 'user.account_id', 'organization.id', 'workspace.host_paths',
]);
const CONTENT = new Set(['prompt', 'prompt_text', 'response', 'tool_input', 'tool_parameters', 'error']);

function val(v: Record<string, unknown> | undefined): unknown {
  if (!v) return null;
  if ('stringValue' in v) return v.stringValue;
  if ('intValue' in v) return Number(v.intValue);
  if ('doubleValue' in v) return Number(v.doubleValue);
  if ('boolValue' in v) return v.boolValue;
  if ('arrayValue' in v) return ((v.arrayValue as { values?: Record<string, unknown>[] }).values ?? []).map(val);
  if ('kvlistValue' in v) return attrs(((v.kvlistValue as { values?: KV[] }).values ?? []), false);
  return null;
}

// Plain object from OTLP attributes, with identity/content scrubbing applied.
function attrs(list: KV[] | undefined, scrub = true): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const { key, value } of list ?? []) {
    if (scrub) {
      if (DROP.has(key)) continue;
      if (CONTENT.has(key) && value?.stringValue !== '<REDACTED>') continue;
    }
    out[key] = key === 'hook_name' && scrub
      ? createHash('sha256').update(String(val(value))).digest('hex').slice(0, 12)
      : val(value);
  }
  return out;
}

const ms = (ns: unknown) => (ns ? Number(BigInt(String(ns)) / 1000000n) : Date.now());
const str = (v: unknown) => (v == null ? null : String(v));
const machine = (os: unknown) => (os === 'darwin' ? 'mac' : os === 'windows' ? 'pc' : str(os));

type Rec = Record<string, any>; // OTLP JSON is untrusted; fields are probed defensively

export function parse(path: string, body: unknown): Row[] {
  const rows: Row[] = [];
  const b = (body ?? {}) as Rec;
  if (path === '/v1/logs') {
    for (const rl of b.resourceLogs ?? []) {
      const res = attrs(rl.resource?.attributes);
      for (const sl of rl.scopeLogs ?? []) for (const lr of sl.logRecords ?? []) {
        const a = attrs(lr.attributes);
        const name = String(a['event.name'] ?? lr.body?.stringValue ?? '');
        const { 'session.id': sid, 'prompt.id': pid, request_id: rid, ...rest } = a;
        rows.push({
          kind: 'event', name, ts: ms(lr.timeUnixNano), session_id: str(sid), prompt_id: str(pid),
          request_id: str(rid), machine: machine(res['os.type']), value: null, attrs: JSON.stringify(rest),
        });
      }
    }
  } else if (path === '/v1/metrics') {
    for (const rm of b.resourceMetrics ?? []) {
      const res = attrs(rm.resource?.attributes);
      for (const sm of rm.scopeMetrics ?? []) for (const m of sm.metrics ?? []) {
        const kind = m.sum ?? m.gauge ?? m.histogram;
        for (const dp of kind?.dataPoints ?? []) {
          const a = attrs(dp.attributes);
          const { 'session.id': sid, ...rest } = a;
          if (dp.count !== undefined) rest.count = Number(dp.count);
          const v = dp.asInt ?? dp.asDouble ?? dp.sum;
          rows.push({
            kind: 'metric', name: m.name, ts: ms(dp.timeUnixNano), session_id: str(sid), prompt_id: null,
            request_id: null, machine: machine(res['os.type']), value: v == null ? null : Number(v),
            attrs: JSON.stringify(rest),
          });
        }
      }
    }
  }
  return rows;
}
