import test from 'node:test';
import assert from 'node:assert/strict';
import { parseFailures, caughtByTrend } from '../failures.ts';

const md = [
  '# Failures log',
  '',
  'Format: `YYYY-MM-DD | session | class | caught_by | what | evidence | topic`',
  '',
  'date | session | class | caught_by | what',
  '--- | --- | --- | --- | ---',
  '2026-01-05 | s-aaa | scope | Him | did extra work',
  '2026-01-06 | s-bbb | wrong-claim | me | said X | file.ts:3 | topic-one',
  '2026-01-14 | slug-c | skipped-test | Verifier | no test run | log | topic-two',
  'Some prose line mentioning 2026-01-07 | not | a | row | really',
  '2026-01-07 | too | short',
  '',
].join('\n');

test('parseFailures tolerates 5- and 7-field rows, skips non-rows', () => {
  const r = parseFailures(md);
  assert.equal(r.length, 3);
  assert.deepEqual(r[0], {
    date: '2026-01-05', session: 's-aaa', class: 'scope', caught_by: 'him',
    what: 'did extra work', evidence: null, topic: null,
  });
  assert.equal(r[1].evidence, 'file.ts:3');
  assert.equal(r[1].topic, 'topic-one');
  assert.equal(r[2].caught_by, 'verifier');
});

test('caughtByTrend counts per ISO week', () => {
  const t = caughtByTrend(parseFailures(md));
  assert.deepEqual(t, {
    '2026-W02': { him: 1, me: 1 },
    '2026-W03': { verifier: 1 },
  });
});

test('ISO week year boundary', () => {
  const t = caughtByTrend([{ date: '2027-01-01', caught_by: 'me' }] as never);
  assert.deepEqual(t, { '2026-W53': { me: 1 } });
});
