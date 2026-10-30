// Regenerates the synthetic fixtures: node test/fixtures/make.mjs
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = dirname(fileURLToPath(import.meta.url));
const S = 'session date started ended duration_s active_s project assistant_msgs interruptions tool_errors denials generated_edits tokens_in tokens_out cache_read cache_create thinking models result_bytes context_read_bytes code_read_bytes'.split(' ');
const U = 'session date project agent activity requests output thinking cost_usd effort'.split(' ');
const t = (a) => a.join('\t');
const srow = (id, project, out, models) =>
  t([id, '2026-10-20', '2026-10-20T10:00:00', '2026-10-20T11:00:00', 3600, 1800, project, 10, 1, 2, 0, 0, 100, out, 1000, 200, 5, models, 0, 0, 0]);
const sess = (rows) => ['# Written by a synthetic fixture', '# ' + t(S), ...rows, t(S)].join('\n') + '\n';
const use = (rows) => ['# cost_usd = the whole request at PRICES as of 2026-10-28.', '# ' + t(U), ...rows].join('\n') + '\n';
const urow = (...a) => t(a);

mkdirSync(join(dir, 'pc'), { recursive: true });
writeFileSync(join(dir, 'sessions.tsv'), sess([
  srow('s-single', '-Users-alice-www-projects-epicerie', 50, 'claude-opus-5-5'),
  srow('s-single/ag1', '-Users-alice-www-projects-epicerie', 5, 'claude-opus-5-5'),
  srow('s-mixed', '-Users-alice-www', 30, 'claude-opus-5-5,claude-haiku-4-5'),
  srow('s-syn', '-private-tmp', 0, '<synthetic>'),
  t(srow('s-ragged', 'M--', 20, 'claude-opus-5-5').split('\t').slice(0, 20)),
]));
writeFileSync(join(dir, 'pc/sessions.tsv'), sess([srow('p1', 'M--projects-epicerie', 70, 'claude-opus-5-5')].slice(0, 1)).replace(/\n[^\n]*\n$/, '\n'));
writeFileSync(join(dir, 'usage.tsv'), use([
  urow('s-single', '2026-10-20', '-Users-alice-www-projects-epicerie', 'main', 'coding', 4, 50, 5, 0.5, 'high'),
  urow('s-single', '2026-10-20', '-Users-alice-www-projects-epicerie', 'main', 'answering', 1, 10, 0, 0.1), // pre-effort row: no trailing column
  urow('s-mixed', '2026-10-20', '-Users-alice-www', 'headless', 'answering', 1, 1, 0, 0.1, ''),
  urow('s-mixed/ag1', '2026-10-20', '-Users-alice-www', 'subagent:Explore', 'coding', 2, 10, 0, 0.2, 'medium'),
  t(U),
]));
writeFileSync(join(dir, 'pc/usage.tsv'), use([urow('p1', '2026-10-20', 'M--projects-epicerie', 'main', 'coding', 3, 10, 0, 0.3, 'low')]));
