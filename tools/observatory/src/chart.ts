// Chart helpers. Chart x is local wall clock read as UTC: a day or an
// `YYYY-MM-DDTHH:MM` timestamp becomes epoch seconds with no timezone shift.
import type { DayStat, Tile } from './metrics';
import type { Commit } from './overlay';

export const DAY_S = 86400;

export function xOf(dayOrAt: string): number {
  const iso = dayOrAt.length === 10 ? `${dayOrAt}T00:00:00Z` : `${dayOrAt}:00Z`;
  return Date.parse(iso) / 1000;
}

export function xRange(dates: string[]): [number, number] {
  return [xOf(dates[0]!), xOf(dates[dates.length - 1]!) + DAY_S];
}

// The day whose slot contains the cursor, not the nearest data point.
export function dayAt(xValue: number, x0: number, n: number): number {
  const i = Math.floor((xValue - x0) / DAY_S);
  return Math.min(Math.max(i, 0), n - 1);
}

export function dayBox(i: number, dates: string[]): [number, number] {
  const x = xOf(dates[i]!);
  return [x, x + DAY_S];
}

export function tickFormat(days: number): string {
  return days <= 2 ? '{MMM} {D} {HH}:{mm}' : '{MMM} {D}';
}

// Unit text to print after a headline value; empty when fmtValue already shows it.
export const headlineUnit = (unit: string): string => (['share', 'ratio', 'h/day'].includes(unit) ? '' : unit);

export function fmtValue(x: number | null, unit: string): string {
  if (x === null) return '–';
  if (unit === 'share') return `${Math.round(x * 100)}%`;
  if (unit === 'ratio') return x.toFixed(2);
  if (unit === 'h/day') return `${x.toFixed(1)} h`;
  if (unit.startsWith('per ')) return x.toFixed(1);
  if (Math.abs(x) >= 10000) return `${Math.round(x / 1000)}k`;
  return Number.isInteger(x) ? String(x) : x.toFixed(1);
}

// Null under 3 points, or when the median is 0 (nothing to compare against).
export function median(series: (number | null)[]): number | null {
  const v = series.filter((x): x is number => x !== null).sort((a, b) => a - b);
  if (v.length < 3) return null;
  const mid = Math.floor(v.length / 2);
  const m = v.length % 2 ? v[mid]! : (v[mid - 1]! + v[mid]!) / 2;
  return m === 0 ? null : m;
}

export function deltaText(value: number | null, prev: number | null): string {
  const head = 'vs previous 7 days: ';
  if (value === null || prev === null || prev === 0) return `${head}n/a`;
  const pct = Math.round(((value - prev) / prev) * 100);
  const sign = pct < 0 ? '−' : '+';
  return `${head}${sign}${Math.abs(pct)}%`;
}

export type Mark = { at: string; date: string; subject: string; tags: string[]; color: string };
export type ChartData = { dates: string[]; unit: string; lines: { label: string; data: (number | null)[] }[]; ratio?: { perDay: DayStat[] }; effortRequests?: number[] };

// Commits with a tag in the overlay; colour of the first such tag.
export function buildMarks(commits: Commit[], overlay: string[], colors: Record<string, string>): Mark[] {
  return commits.flatMap((c) => {
    const tag = c.tags.find((t) => overlay.includes(t));
    return tag === undefined ? [] : [{ at: c.at, date: c.date, subject: c.subject, tags: c.tags, color: colors[tag]! }];
  });
}

export const monthDay = (dayOrAt: string) => new Date(xOf(dayOrAt) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });

export const whenOf = (at: string) => `${monthDay(at)} ${at.slice(11, 16)}`;

export const markTip = (m: Mark) => `${whenOf(m.at)} · ${m.tags.join(', ')} · ${m.subject.slice(0, 70)}`;

const marksOn = (day: string, marks: Mark[]) => marks.filter((x) => x.date === day).sort((a, b) => a.at.localeCompare(b.at)).map(markTip);

export function tooltipLines(i: number, c: ChartData, marks: Mark[]): string[] {
  const day = c.dates[i]!;
  const out = [monthDay(day)];
  const stat = c.ratio?.perDay[i];
  if (stat?.lowN) out.push('fewer than 5 sessions, not plotted');
  else {
    for (const l of c.lines) out.push(`${l.label}: ${fmtValue(l.data[i] ?? null, c.unit)}`);
    if (stat) {
      const [lo, hi] = stat.iqr ?? [null, null];
      out.push(`n ${stat.n} · middle half ${fmtValue(lo, c.unit)}–${fmtValue(hi, c.unit)} · largest session ${fmtValue(stat.largestShare, 'share')}`);
    }
    if (c.effortRequests) out.push(`requests: ${c.effortRequests[i]}`);
  }
  return [...out, ...marksOn(day, marks)];
}

// Stacked-bar tooltip: date, each source, total, then the commits that day.
export function stackTip(i: number, dates: string[], series: [string, number[]][], marks: Mark[]): string[] {
  const day = dates[i]!;
  const total = series.reduce((a, [, v]) => a + v[i]!, 0);
  return [monthDay(day), ...series.map(([name, v]) => `${name}: ${v[i]}`), `total: ${total}`, ...marksOn(day, marks)];
}

// Tooltips near the left or right edge anchor to that edge so they stay on the card.
export const tipAnchor = (i: number, n: number): 'left' | 'center' | 'right' => (i < n / 3 ? 'left' : i >= (2 * n) / 3 ? 'right' : 'center');

export const tips = (c: ChartData, marks: Mark[]) => c.dates.map((_, i) => tooltipLines(i, c, marks));

export function chartOf(t: Tile): ChartData {
  if (t.effort) return { dates: t.dates, unit: 'share', lines: Object.entries(t.effort).map(([label, data]) => ({ label, data })), effortRequests: t.effortRequests };
  const lines = [{ label: t.title, data: t.series }];
  return t.ratio ? { dates: t.dates, unit: t.unit, lines, ratio: { perDay: t.ratio.perDay } } : { dates: t.dates, unit: t.unit, lines };
}
