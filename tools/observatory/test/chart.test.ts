import { expect, it } from 'vitest';
import { buildMarks, dayAt, dayBox, deltaText, fmtValue, headlineUnit, markTip, median, stackTip, tickFormat, tipAnchor, tooltipLines, whenOf, xOf, xRange } from '../src/chart';
const D = ['2026-10-27', '2026-10-28'];
it('x convention and range include the whole last day', () => {
  expect(xOf('2026-10-28')).toBe(Date.parse('2026-10-28T00:00:00Z') / 1000);
  expect(xOf('2026-10-28T14:05')).toBe(Date.parse('2026-10-28T14:05:00Z') / 1000);
  const [lo, hi] = xRange(D);
  expect(lo).toBe(xOf('2026-10-27'));
  expect(xOf('2026-10-28T14:05')).toBeLessThan(hi);
  expect(hi).toBe(xOf('2026-10-29'));
});
it('dayAt picks the day that contains the cursor, not the nearest point', () => {
  const x0 = xOf(D[0]!);
  expect(dayAt(xOf('2026-10-27T00:00'), x0, 2)).toBe(0);
  expect(dayAt(xOf('2026-10-27T14:05'), x0, 2)).toBe(0);
  expect(dayAt(xOf('2026-10-27T23:59'), x0, 2)).toBe(0);
  expect(dayAt(xOf('2026-10-28T14:05'), x0, 2)).toBe(1);
  expect(dayAt(xOf('2026-10-30T01:00'), x0, 2)).toBe(1);
  expect(dayAt(x0 - 10, x0, 2)).toBe(0);
});
it('dayBox spans midnight to midnight', () => {
  expect(dayBox(1, D)).toEqual([xOf('2026-10-28'), xOf('2026-10-29')]);
});
it('tick format adds the time only for windows of 2 days or less', () => {
  expect(tickFormat(2)).toBe('{MMM} {D} {HH}:{mm}');
  expect(tickFormat(3)).toBe('{MMM} {D}');
});
it('formats values by unit', () => {
  expect(fmtValue(0.75, 'share')).toBe('75%');
  expect(fmtValue(0.8234, 'ratio')).toBe('0.82');
  expect(fmtValue(2.14, 'h/day')).toBe('2.1 h');
  expect(fmtValue(3.44, 'per 100 requests')).toBe('3.4');
  expect(fmtValue(1.26, 'per hour')).toBe('1.3');
  expect(fmtValue(12345, 'tokens')).toBe('12k');
  expect(fmtValue(3, 'sessions/day')).toBe('3');
  expect(fmtValue(2.5, 'sessions/day')).toBe('2.5');
  expect(fmtValue(null, 'ratio')).toBe('–');
});
it('median ignores nulls; null under 3 points or when 0', () => {
  expect(median([1, null, 3, 2])).toBe(2);
  expect(median([1, 2, 3, 4])).toBe(2.5);
  expect(median([1, null, 2])).toBeNull();
  expect(median([0, 0, 0, 5])).toBeNull();
});
it('delta text', () => {
  expect(deltaText(11.2, 10)).toBe('vs previous 7 days: +12%');
  expect(deltaText(9, 10)).toBe('vs previous 7 days: −10%');
  expect(deltaText(9, null)).toBe('vs previous 7 days: n/a');
  expect(deltaText(9, 0)).toBe('vs previous 7 days: n/a');
  expect(deltaText(null, 10)).toBe('vs previous 7 days: n/a');
});
const C = (subject: string, at: string, tags = ['settings']) => ({ hash: subject, at, date: at.slice(0, 10), subject, tags });
it('whenOf', () => expect(whenOf('2026-10-28T09:05')).toBe('Oct 28 09:05'));
it('buildMarks follows the overlay filter and keeps time and subject', () => {
  const ms = buildMarks([C('a', '2026-10-28T14:05'), C('b', '2026-10-28T09:00', ['scripts'])], ['settings'], { settings: '#00838f', scripts: '#7b1fa2' });
  expect(ms).toEqual([{ at: '2026-10-28T14:05', date: '2026-10-28', subject: 'a', tags: ['settings'], color: '#00838f' }]);
});
it('markTip', () => {
  expect(markTip({ at: '2026-10-28T14:05', date: '2026-10-28', subject: 'x'.repeat(90), tags: ['settings'], color: '' }))
    .toBe(`Oct 28 14:05 · settings · ${'x'.repeat(70)}`);
});
const stat = (o = {}) => ({ n: 6, lowN: false, largestShare: 0.4, iqr: [1, 3] as [number, number], ...o });
const ratio = { dates: ['2026-10-27', '2026-10-28'], unit: 'per 100 requests', lines: [{ label: 'Tool error rate', data: [2.04, null] }], ratio: { perDay: [stat(), stat({ n: 2, lowN: true })] } };
it('ratio tooltip: date, value, n / middle half / largest share, then commits by time', () => {
  const marks = buildMarks([C('late', '2026-10-27T18:00'), C('early', '2026-10-27T08:30'), C('other day', '2026-10-28T01:00')], ['settings'], { settings: '#0' });
  expect(tooltipLines(0, ratio, marks)).toEqual([
    'Oct 27',
    'Tool error rate: 2.0',
    'n 6 · middle half 1.0–3.0 · largest session 40%',
    'Oct 27 08:30 · settings · early',
    'Oct 27 18:00 · settings · late',
  ]);
});
it('low-n day says it is not plotted', () => {
  expect(tooltipLines(1, ratio, [])).toEqual(['Oct 28', 'fewer than 5 sessions, not plotted']);
});
it('effort tooltip lists every level and the request count', () => {
  const eff = { dates: ['2026-10-28'], unit: 'share', lines: [{ label: 'high', data: [0.75] }, { label: 'not set', data: [0.25] }], effortRequests: [4] };
  expect(tooltipLines(0, eff, [])).toEqual(['Oct 28', 'high: 75%', 'not set: 25%', 'requests: 4']);
});
it('stack tooltip: date, each source, total, commits', () => {
  const m = buildMarks([C('fix', '2026-10-28T14:05')], ['settings'], { settings: '#0' });
  expect(stackTip(0, ['2026-10-28'], [['config', [3]], ['user', [2]]], m))
    .toEqual(['Oct 28', 'config: 3', 'user: 2', 'total: 5', 'Oct 28 14:05 · settings · fix']);
});
it('tooltip anchor by column third', () => {
  expect([0, 9, 10, 19, 20, 29].map((i) => tipAnchor(i, 30))).toEqual(['left', 'left', 'center', 'center', 'right', 'right']);
});
it('headline unit shows only when fmtValue does not already', () => {
  expect(headlineUnit('share')).toBe('');
  expect(headlineUnit('h/day')).toBe('');
  expect(headlineUnit('ratio')).toBe('');
  expect(headlineUnit('per 100 requests')).toBe('per 100 requests');
});
