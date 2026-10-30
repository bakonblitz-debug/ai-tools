import { defineConfig } from 'vitest/config';

// The dashboard's tests only; receiver/ (own vitest) and analysis/ (node:test) run their own.
export default defineConfig({ test: { include: ['test/**/*.test.ts'] } });
