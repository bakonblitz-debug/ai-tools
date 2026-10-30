import test from 'node:test';
import assert from 'node:assert/strict';
import { bands } from '../anomaly.ts';

test('flat-ish series has no anomalies', () => {
  const s = Array.from({ length: 30 }, (_, i) => 10 + (i % 3));
  assert.equal(bands(s).filter((b) => b?.anomaly).length, 0);
});

test('one spike is flagged', () => {
  const s = Array.from({ length: 30 }, (_, i) => 10 + (i % 3));
  s[20] = 100;
  const out = bands(s);
  assert.deepEqual(out.flatMap((b, i) => (b?.anomaly ? [i] : [])), [20]);
});

test('MAD 0: different value is anomaly, equal is not', () => {
  const s = [5, 5, 5, 5, 5, 5, 5, 5, 6, 5];
  const out = bands(s);
  assert.equal(out[7].anomaly, false);
  assert.equal(out[8].anomaly, true);
  assert.equal(out[8].lo, 5);
  assert.equal(out[8].hi, 5);
});

test('warm-up: fewer than 7 prior points has no band', () => {
  const out = bands([1, 2, 3, 4, 5, 6, 1000, 1]);
  for (let i = 0; i < 7; i++) {
    assert.equal(out[i].lo, null);
    assert.equal(out[i].anomaly, false);
  }
  assert.notEqual(out[7].lo, null);
});

test('nulls stay null and are skipped in the window', () => {
  const s: (number | null)[] = [1, null, 1, 1, null, 1, 1, 1, 1, 50];
  const out = bands(s);
  assert.equal(out[1], null);
  assert.equal(out[4], null);
  assert.equal(out[8]!.lo, null); // only 6 prior non-null points
  assert.equal(out[9]!.anomaly, true);
});

test('window limits history to the previous N points', () => {
  const s = [...Array(10).fill(0), ...Array(10).fill(100), 100];
  const out = bands(s, 10);
  assert.equal(out[20]!.median, 100);
  assert.equal(out[20]!.anomaly, false);
});
