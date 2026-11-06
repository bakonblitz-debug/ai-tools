import { expect, it } from 'vitest';
import { parseGitLog, sinceFor } from '../src/overlay';
const H = 'a'.repeat(40);
const log = `${H}\t2026-10-28T23:30:00-04:00\tsettings: x\nconfig/a.json\n`;
it('keeps the commit time in the dashboard zone', () => {
  const [c] = parseGitLog(log, '2026-10-01', '2026-10-31', 'America/Toronto');
  expect(c).toMatchObject({ at: '2026-10-28T23:30', date: '2026-10-28', tags: ['settings'] });
});
it('converts to UTC and filters the window on the converted date', () => {
  expect(parseGitLog(log, '2026-10-01', '2026-10-31', 'UTC')[0]!.at).toBe('2026-10-29T03:30');
  expect(parseGitLog(log, '2026-10-01', '2026-10-28', 'UTC')).toEqual([]);
});
it('starts the git window two days before the first day', () => {
  expect(sinceFor('2026-10-01')).toBe('2026-09-29');
  expect(sinceFor('2026-03-02')).toBe('2026-02-28');
});
