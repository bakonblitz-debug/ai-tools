import test from 'node:test';
import assert from 'node:assert/strict';
import { budget } from '../budget.ts';

const days = [
  { date: '2026-10-01', num: 2, den: 100 },
  { date: '2026-10-02', num: 10, den: 100 },
  { date: '2026-10-03', num: 0, den: 0 },
  { date: '2026-10-09', num: 99, den: 1 }, // outside period
];
const period = { from: '2026-10-01', to: '2026-10-05' };

test('pooled value, used %, days over, status', () => {
  const r = budget(days, 5, period, 100);
  assert.equal(r.actual, 6); // 12 / 200 * 100
  assert.equal(r.used_pct, 120);
  assert.equal(r.days_over, 1); // den 0 day not counted
  assert.equal(r.days, 2);
  assert.equal(r.status, 'over');
});

test('warn at 80%, ok below', () => {
  assert.equal(budget([{ date: '2026-10-01', num: 4, den: 100 }], 5, period, 100).status, 'warn');
  assert.equal(budget([{ date: '2026-10-01', num: 3, den: 100 }], 5, period, 100).status, 'ok');
  assert.equal(budget([{ date: '2026-10-01', num: 5, den: 100 }], 5, period, 100).status, 'over');
});

test('empty period and den 0 only', () => {
  const e = budget([], 5, period);
  assert.deepEqual(e, { actual: null, used_pct: null, days_over: 0, days: 0, status: 'nodata' });
  assert.equal(budget([{ date: '2026-10-01', num: 0, den: 0 }], 5, period).status, 'nodata');
});
