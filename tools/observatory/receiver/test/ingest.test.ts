import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parse } from '../ingest.ts';

const batches: { path: string; body: unknown }[] = JSON.parse(
  readFileSync(new URL('./fixtures/otel-headless.json', import.meta.url), 'utf8'),
);
const all = batches.flatMap((b) => parse(b.path, b.body));

const s = (v: string) => ({ stringValue: v });
const logBody = (attrs: { key: string; value: unknown }[], os = 'darwin') => ({
  resourceLogs: [
    {
      resource: { attributes: [{ key: 'os.type', value: s(os) }] },
      scopeLogs: [{ logRecords: [{ timeUnixNano: '1793394689019000000', body: s('claude_code.x'), attributes: attrs }] }],
    },
  ],
});

describe('parse', () => {
  it('turns every fixture batch into rows', () => {
    for (const b of batches) expect(parse(b.path, b.body).length).toBeGreaterThan(0);
    expect(all.some((r) => r.kind === 'metric')).toBe(true);
  });

  it('keeps api_request fields', () => {
    const r = all.find((x) => x.kind === 'event' && x.name === 'api_request')!;
    expect(r).toBeTruthy();
    expect(r.request_id).toBeTruthy();
    const a = JSON.parse(r.attrs);
    for (const k of ['model', 'effort', 'cost_usd', 'input_tokens', 'output_tokens', 'query_source'])
      expect(a).toHaveProperty(k);
    expect(typeof a.input_tokens).toBe('number');
  });

  it('has no identity key anywhere', () => {
    const txt = JSON.stringify(all);
    for (const k of ['user.email', 'user.id', 'user.account_uuid', 'user.account_id', 'organization.id', 'workspace.host_paths'])
      expect(txt).not.toContain(`"${k}"`);
    expect(txt).not.toContain('user@example.com');
  });

  it('hashes hook_name', () => {
    const h = all.filter((r) => JSON.parse(r.attrs).hook_name !== undefined);
    expect(h.length).toBeGreaterThan(0);
    for (const r of h) expect(JSON.parse(r.attrs).hook_name).toMatch(/^[0-9a-f]{12}$/);
  });

  it('drops content attributes unless <REDACTED>', () => {
    const rows = parse('/v1/logs', logBody([
      { key: 'prompt', value: s('secret text') },
      { key: 'response', value: s('<REDACTED>') },
      { key: 'error', value: s('boom') },
    ]));
    const a = JSON.parse(rows[0].attrs);
    expect(a).not.toHaveProperty('prompt');
    expect(a).not.toHaveProperty('error');
    expect(a.response).toBe('<REDACTED>');
  });

  it('converts intValue and maps machine', () => {
    const rows = parse('/v1/logs', logBody([{ key: 'n', value: { intValue: '42' } }], 'windows'));
    expect(JSON.parse(rows[0].attrs).n).toBe(42);
    expect(rows[0].machine).toBe('pc');
    expect(parse('/v1/logs', logBody([], 'darwin'))[0].machine).toBe('mac');
    expect(parse('/v1/logs', logBody([], 'linux'))[0].machine).toBe('linux');
  });

  it('parses metric data points and scrubs their attributes', () => {
    const rows = parse('/v1/metrics', {
      resourceMetrics: [{
        resource: { attributes: [{ key: 'os.type', value: s('darwin') }] },
        scopeMetrics: [{ metrics: [{ name: 'm', sum: { dataPoints: [{
          timeUnixNano: '1', asInt: '7',
          attributes: [{ key: 'user.email', value: s('a@b.c') }, { key: 'session.id', value: s('S') }, { key: 'k', value: s('v') }],
        }] } }] }],
      }],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: 'metric', name: 'm', value: 7, session_id: 'S', machine: 'mac' });
    expect(rows[0].attrs).not.toContain('user.email');
  });
});
