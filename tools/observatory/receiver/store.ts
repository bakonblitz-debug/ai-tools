import Database from 'better-sqlite3';
import type { Row } from './ingest.ts';

export function open(dbPath: string) {
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('busy_timeout = 5000');
  db.exec(`
    create table if not exists otel_events (
      id integer primary key, received_at integer not null, name text not null, ts integer not null,
      session_id text, prompt_id text, request_id text, machine text, attrs text not null);
    create table if not exists otel_metrics (
      id integer primary key, received_at integer not null, name text not null, ts integer not null,
      session_id text, machine text, value real, attrs text not null);
    create index if not exists otel_events_ts on otel_events(ts);
    create index if not exists otel_metrics_ts on otel_metrics(ts);
  `);
  const ev = db.prepare(
    'insert into otel_events (received_at,name,ts,session_id,prompt_id,request_id,machine,attrs) values (?,?,?,?,?,?,?,?)');
  const me = db.prepare(
    'insert into otel_metrics (received_at,name,ts,session_id,machine,value,attrs) values (?,?,?,?,?,?,?)');
  const tx = db.transaction((rows: Row[]) => {
    const now = Date.now();
    for (const r of rows)
      if (r.kind === 'event') ev.run(now, r.name, r.ts, r.session_id, r.prompt_id, r.request_id, r.machine, r.attrs);
      else me.run(now, r.name, r.ts, r.session_id, r.machine, r.value, r.attrs);
  });
  return Object.assign(db, { insert: (rows: Row[]) => tx(rows) });
}
