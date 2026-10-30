import test from 'node:test';
import assert from 'node:assert/strict';
import { costTable, errorTable } from '../routing.ts';

test('costTable groups, excludes null model, maps effort, sorts by cost', () => {
  const sessions = [
    { session: 's1', model: 'opus' },
    { session: 's2', model: 'opus' },
    { session: 's3', model: 'haiku' },
    { session: 's4', model: null },
  ];
  const usage = [
    { session: 's1', activity: 'coding', requests: '10', output: '1000', cost_usd: '2', effort: 'high' },
    { session: 's1/agentA', activity: 'coding', requests: 10, output: 500, cost_usd: 1, effort: 'high' },
    { session: 's2', activity: 'coding', requests: 5, output: 500, cost_usd: 1, effort: 'high' },
    { session: 's2', activity: 'chat', requests: 4, output: 400, cost_usd: 0.5, effort: '' },
    { session: 's3', activity: 'chat', requests: 100, output: 1000, cost_usd: 0.1, effort: '' },
    { session: 's4', activity: 'chat', requests: 9, output: 9, cost_usd: 9, effort: '' },
    { session: 'zz', activity: 'chat', requests: 9, output: 9, cost_usd: 9, effort: '' },
  ];
  const t = costTable(usage, sessions);
  assert.equal(t.length, 3);
  assert.deepEqual(t[0], {
    model: 'opus', effort: 'high', activity: 'coding',
    requests: 25, cost_usd: 4, cost_per_request: 0.16, output_per_request: 80, sessions: 2,
  });
  assert.deepEqual(t.map((r) => r.cost_usd), [4, 0.5, 0.1]);
  assert.equal(t[1].effort, 'not set');
  assert.equal(t[1].sessions, 1);
  assert.equal(t[2].model, 'haiku');
  assert.equal(t[2].cost_per_request, 0.001);
});

const ev = (name: string, request_id: string | null, attrs: object = {}) => ({ name, request_id, attrs: JSON.stringify(attrs) });

test('errorTable per 100 requests, with unknown bucket', () => {
  const events = [
    ev('api_request', 'r1', { model: 'opus', effort: 'high' }),
    ev('api_request', 'r2', { model: 'opus', effort: 'high' }),
    ev('api_request', 'r3', { model: 'opus', effort: 'high' }),
    ev('api_request', 'r4', { model: 'opus', effort: 'high' }),
    ev('api_request', 'r5', { model: 'haiku' }),
    ev('tool_result', 'r1', { success: 'false' }),
    ev('tool_result', 'r1', { success: 'false' }),
    ev('tool_result', 'r2', { success: 'true' }),
    ev('tool_result', 'r5', { success: false }),
    ev('tool_result', 'rX', { success: 'false' }),
    ev('api_error', 'r3', { model: 'opus', effort: 'high' }),
    ev('api_refusal', 'r4', {}),
    ev('api_refusal', null, {}),
  ];
  const t = errorTable(events);
  const get = (m: string, e: string) => t.find((r) => r.model === m && r.effort === e)!;
  assert.deepEqual(get('opus', 'high'), {
    model: 'opus', effort: 'high', requests: 4,
    tool_errors_per_100: 50, api_errors_per_100: 25, refusals_per_100: 25,
  });
  assert.deepEqual(get('haiku', 'not set'), {
    model: 'haiku', effort: 'not set', requests: 1,
    tool_errors_per_100: 100, api_errors_per_100: 0, refusals_per_100: 0,
  });
  const u = get('unknown', 'unknown');
  assert.equal(u.requests, 0);
  assert.equal(u.tool_errors_per_100, null);
});
