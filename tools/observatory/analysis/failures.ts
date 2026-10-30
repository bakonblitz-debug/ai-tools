export type Failure = {
  date: string; session: string; class: string; caught_by: string; what: string;
  evidence: string | null; topic: string | null;
};

export function parseFailures(markdown: string): Failure[] {
  const out: Failure[] = [];
  for (const line of markdown.split(/\r?\n/)) {
    const f = line.split(' | ').map((x) => x.trim());
    if (f.length < 5 || f.length > 7 || !/^\d{4}-\d{2}-\d{2}$/.test(f[0])) continue;
    out.push({
      date: f[0], session: f[1], class: f[2], caught_by: f[3].toLowerCase(), what: f[4],
      evidence: f[5] || null, topic: f[6] || null,
    });
  }
  return out;
}

// ISO 8601 week label, e.g. 2026-W02
function isoWeek(date: string): string {
  const d = new Date(date + 'T00:00:00Z');
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day); // Thursday of this week
  const y = d.getUTCFullYear();
  const week = Math.ceil(((d.getTime() - Date.UTC(y, 0, 1)) / 864e5 + 1) / 7);
  return `${y}-W${String(week).padStart(2, '0')}`;
}

// ponytail: only the 'week' bucket exists; add month if the UI needs it.
export function caughtByTrend(rows: Pick<Failure, 'date' | 'caught_by'>[], _bucket = 'week') {
  const out: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const w = (out[isoWeek(r.date)] ??= {});
    w[r.caught_by] = (w[r.caught_by] ?? 0) + 1;
  }
  return out;
}
