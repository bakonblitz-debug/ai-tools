import { describe, expect, it } from 'vitest';
import { mkdtempSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import Database from 'better-sqlite3';
import { open } from '../store.ts';
import { backup } from '../backup.ts';

const day = (d: number) => new Date(Date.UTC(2026, 9, d, 12));

describe('backup', () => {
  it('writes one consistent dated copy per day and keeps the newest `keep`', () => {
    const dir = mkdtempSync(join(tmpdir(), 'obs-bk-'));
    const db = open(join(dir, 'otel.db'));
    db.insert([{ kind: 'event', name: 'api_request', ts: 1, session_id: 's', prompt_id: null, request_id: 'r', machine: 'mac', value: null, attrs: '{}' }]);
    const out = join(dir, 'backups');

    expect(backup(db, out, day(1))).toBe(join(out, 'otel-2026-10-01.db'));
    expect(backup(db, out, day(1))).toBeNull(); // same day: already done
    const copy = new Database(join(out, 'otel-2026-10-01.db'), { readonly: true });
    expect((copy.prepare('select count(*) n from otel_events').get() as { n: number }).n).toBe(1);
    copy.close();

    for (let d = 2; d <= 9; d++) backup(db, out, day(d), 7);
    expect(readdirSync(out).sort()).toEqual([3, 4, 5, 6, 7, 8, 9].map((d) => `otel-2026-10-0${d}.db`));
  });
});
