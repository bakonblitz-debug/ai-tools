import { createServer as http } from 'node:http';
import { timingSafeEqual, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { open } from './store.ts';
import { parse } from './ingest.ts';
import { backup } from './backup.ts';

const LIMIT = 5 * 1024 * 1024;
const sha = (s: string) => createHash('sha256').update(s).digest();

export function createServer(db: ReturnType<typeof open>, key: string) {
  const want = sha(key);
  return http((req, res) => {
    const send = (code: number, body = '{}') => {
      res.writeHead(code, { 'content-type': 'application/json', connection: 'close' }).end(body);
    };
    const path = (req.url ?? '').split('?')[0];
    if (req.method !== 'POST' || (path !== '/v1/logs' && path !== '/v1/metrics')) return send(404);
    const got = String(req.headers['x-observatory-key'] ?? '');
    if (!timingSafeEqual(sha(got), want)) return send(401);
    if (!String(req.headers['content-type'] ?? '').toLowerCase().startsWith('application/json')) return send(415);
    const chunks: Buffer[] = [];
    let size = 0;
    req.on('data', (c: Buffer) => {
      size += c.length;
      if (size > LIMIT) {
        send(413);
        req.destroy();
      } else chunks.push(c);
    });
    req.on('end', () => {
      if (size > LIMIT) return;
      let body: unknown;
      try {
        body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      } catch {
        return send(400);
      }
      try {
        db.insert(parse(path, body));
        send(200);
      } catch {
        send(500); // never log bodies
      }
    });
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const key = process.env.OBSERVATORY_KEY;
  if (!key) {
    console.error('OBSERVATORY_KEY is required');
    process.exit(1);
  }
  const port = Number(process.env.RECEIVER_PORT ?? 4318);
  const db = open(process.env.DB_PATH ?? './otel.db');
  createServer(db, key).listen(port, () => console.log(`receiver listening on ${port}`));
  const dir = process.env.BACKUP_DIR;
  if (dir) {
    const run = () => {
      try {
        const f = backup(db, dir);
        if (f) console.log(`backup written: ${f}`);
      } catch (e) {
        console.error(`backup failed: ${(e as Error).message}`);
      }
    };
    run();
    setInterval(run, 6 * 3600 * 1000); // a new file once per day; the check is cheap
  }
}
