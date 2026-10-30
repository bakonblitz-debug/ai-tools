import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { AddressInfo } from 'node:net';
import type { Server } from 'node:http';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createServer } from '../server.ts';
import { open } from '../store.ts';
import { parse } from '../ingest.ts';

const batches: { path: string; body: unknown }[] = JSON.parse(
  readFileSync(new URL('./fixtures/otel-headless.json', import.meta.url), 'utf8'),
);
const KEY = 'test-key';
let dir: string, server: Server, base: string, db: ReturnType<typeof open>;

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), 'rcv-'));
  db = open(join(dir, 'otel.db'));
  server = createServer(db, KEY);
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
afterAll(() => {
  server.close();
  db.close();
  rmSync(dir, { recursive: true, force: true });
});

const post = (path: string, body: string, headers: Record<string, string> = {}) =>
  fetch(base + path, { method: 'POST', body, headers: { 'content-type': 'application/json', 'x-observatory-key': KEY, ...headers } });

describe('server', () => {
  it('401 without or with wrong key', async () => {
    expect((await post('/v1/logs', '{}', { 'x-observatory-key': '' })).status).toBe(401);
    expect((await post('/v1/logs', '{}', { 'x-observatory-key': 'nope' })).status).toBe(401);
  });
  it('404 other path', async () => expect((await post('/v1/traces', '{}')).status).toBe(404));
  it('415 non-JSON', async () => expect((await post('/v1/logs', 'x', { 'content-type': 'text/plain' })).status).toBe(415));
  it('400 bad JSON', async () => expect((await post('/v1/logs', '{nope')).status).toBe(400));
  it('413 oversize', async () => expect((await post('/v1/logs', ' '.repeat(5 * 1024 * 1024 + 1))).status).toBe(413));

  it('refuses to start without OBSERVATORY_KEY', () => {
    const r = spawnSync(process.execPath, ['--experimental-strip-types', 'server.ts'], {
      cwd: fileURLToPath(new URL('..', import.meta.url)),
      env: { PATH: process.env.PATH, DB_PATH: join(dir, 'x.db') },
    });
    expect(r.status).toBe(1);
  });

  it('200 for fixture and stores expected counts', async () => {
    let ev = 0, me = 0;
    for (const b of batches) {
      for (const r of parse(b.path, b.body)) r.kind === 'event' ? ev++ : me++;
      const res = await post(b.path, JSON.stringify(b.body));
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual({});
    }
    const c = (t: string) => (db.prepare(`select count(*) n from ${t}`).get() as { n: number }).n;
    expect(c('otel_events')).toBe(ev);
    expect(c('otel_metrics')).toBe(me);
    expect(ev + me).toBeGreaterThan(0);
  });
});
