import { expect, it } from 'vitest';
import { isScratch, normalizeProject } from '../src/project';

const env = { WORKSPACE_PREFIXES: '-Users-alice-www,M-', HOME_PREFIXES: '-Users-alice,C--Users-alice' };

it.each([
  ['-Users-alice-www', '(workspace)'],
  ['-Users-alice-www-', '(workspace)'],
  ['M--', '(workspace)'],
  ['M-', '(workspace)'],
  ['-Users-alice-www-projects-epicerie', 'projects-epicerie'],
  ['M--projects-epicerie', 'projects-epicerie'],
  ['/m/x/y', 'x-y'],
  ['/m', '(workspace)'],
  ['/m/', '(workspace)'],
  ['-Users-alice', '~'],
  ['C--Users-alice', '~'],
  ['-Users-bob-other', '-Users-bob-other'],
])('normalizes %s', (raw, want) => expect(normalizeProject(raw, env)).toBe(want));

it.each([
  ['-private-tmp', true],
  ['-private-var-folders-x-T-foo', true],
  ['C--Users-alice-AppData-Local-Temp-foo', true],
  ['C--WINDOWS-system32', true],
  ['-Users-alice-www-projects-epicerie', false],
])('scratch %s', (raw, want) => expect(isScratch(raw)).toBe(want));
