export type Day = { date: string; num: number; den: number };

// Ratio budget over {from,to} (inclusive YYYY-MM-DD). `per` scales the ratio to the target's unit (100 = per 100).
export function budget(series: Day[], target: number, period: { from: string; to: string }, per = 1) {
  const days = series.filter((d) => d.date >= period.from && d.date <= period.to && d.den > 0);
  if (!days.length) return { actual: null, used_pct: null, days_over: 0, days: 0, status: 'nodata' as const };
  const num = days.reduce((s, d) => s + d.num, 0);
  const den = days.reduce((s, d) => s + d.den, 0);
  const actual = (num / den) * per;
  const used_pct = (actual / target) * 100;
  return {
    actual, used_pct,
    days_over: days.filter((d) => (d.num / d.den) * per > target).length,
    days: days.length,
    status: (used_pct >= 100 ? 'over' : used_pct >= 80 ? 'warn' : 'ok') as 'over' | 'warn' | 'ok',
  };
}
