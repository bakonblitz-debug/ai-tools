/** Sessions started per weekday (Mon=0) x hour in `tz`. `started` has no zone suffix and is read as UTC. */
export function startHeatmap(started: (string | null | undefined)[], tz: string): number[][] {
  const grid = Array.from({ length: 7 }, () => Array<number>(24).fill(0));
  const fmt = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short', hour: 'numeric', hourCycle: 'h23' });
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  for (const s of started) {
    if (!s) continue;
    const t = Date.parse(/Z|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z');
    if (Number.isNaN(t)) continue;
    const p = Object.fromEntries(fmt.formatToParts(t).map((x) => [x.type, x.value]));
    grid[days.indexOf(p.weekday!)]![Number(p.hour)]!++;
  }
  return grid;
}
