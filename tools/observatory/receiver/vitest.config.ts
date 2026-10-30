import { defineConfig } from 'vitest/config';

// Own config so vitest does not pick up the dashboard's PostCSS/Tailwind config one level up.
export default defineConfig({ css: { postcss: {} }, test: { include: ['test/**/*.test.ts'] } });
