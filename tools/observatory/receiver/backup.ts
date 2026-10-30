import { mkdirSync, existsSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import type Database from 'better-sqlite3';

// OTel events are source data (nothing can rebuild them), so keep dated copies.
// VACUUM INTO gives a consistent copy while the receiver keeps writing (WAL).
export function backup(db: Database.Database, dir: string, now = new Date(), keep = 7): string | null {
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `otel-${now.toISOString().slice(0, 10)}.db`);
  if (existsSync(file)) return null;
  db.exec(`VACUUM INTO '${file.replaceAll("'", "''")}'`);
  const old = readdirSync(dir).filter((f) => /^otel-\d{4}-\d{2}-\d{2}\.db$/.test(f)).sort().slice(0, -keep);
  for (const f of old) rmSync(join(dir, f));
  return file;
}
