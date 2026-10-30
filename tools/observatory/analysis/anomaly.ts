export type Band = { value: number; median: number | null; lo: number | null; hi: number | null; anomaly: boolean } | null;

const median = (a: number[]): number => {
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// Band per point from the previous `window` non-null points (point itself excluded).
export function bands(series: (number | null)[], window = 14, k = 3): Band[] {
  const prior: number[] = [];
  return series.map((v) => {
    if (v === null) return null;
    const w = prior.slice(-window);
    prior.push(v);
    if (w.length < 7) return { value: v, median: null, lo: null, hi: null, anomaly: false };
    const med = median(w);
    const mad = 1.4826 * median(w.map((x) => Math.abs(x - med)));
    const lo = med - k * mad;
    const hi = med + k * mad;
    return { value: v, median: med, lo, hi, anomaly: v < lo || v > hi };
  });
}
