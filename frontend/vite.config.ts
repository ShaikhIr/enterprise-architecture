/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@app': path.resolve(__dirname, './src/app'),
      '@features': path.resolve(__dirname, './src/features'),
      '@shared': path.resolve(__dirname, './src/shared'),
      '@core': path.resolve(__dirname, './src/core'),
      '@assets': path.resolve(__dirname, './src/assets'),
    },
  },
  test: {
    environment: 'jsdom',
    // No injected globals: the project's own convention (enforced by ESLint's
    // import/order rule) is explicit imports everywhere, so test files import
    // `describe`/`it`/`expect`/`vi` from 'vitest' like any other module.
    globals: false,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    restoreMocks: true,
    // V8 coverage instrumentation adds real per-test overhead, and the
    // PrimeReact Dropdown/Dialog tests already do several DOM round trips
    // (open panel, click option, submit, wait for validation) — comfortably
    // under the 5s default without coverage, but occasionally over it once
    // every statement is being tracked. `npm test` runs uninstrumented, so
    // this only raises the ceiling for `--coverage` runs.
    testTimeout: 10000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.d.ts', 'src/main.tsx', 'src/vite-env.d.ts', 'src/**/index.ts'],
    },
  },
  server: {
    port: 6769,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Generous timeouts for long-running requests such as a bulk employee
        // import, which the dev proxy would otherwise abort.
        timeout: 600000,
        proxyTimeout: 600000,
      },
    },
  },
  // Pre-bundle deps up front so Vite never discovers a new dependency
  // mid-session and forces a full-page reload to re-optimize.
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react-router-dom',
      'react-redux',
      '@reduxjs/toolkit',
      '@tanstack/react-query',
      'axios',
      'react-hook-form',
      '@hookform/resolvers/zod',
      'zod',
      'primereact/api',
      'primereact/avatar',
      'primereact/badge',
      'primereact/button',
      'primereact/calendar',
      'primereact/card',
      'primereact/column',
      'primereact/confirmdialog',
      'primereact/datatable',
      'primereact/dialog',
      'primereact/divider',
      'primereact/dropdown',
      'primereact/inputnumber',
      'primereact/inputswitch',
      'primereact/inputtext',
      'primereact/inputtextarea',
      'primereact/menu',
      'primereact/message',
      'primereact/password',
      'primereact/progressspinner',
      'primereact/tag',
      'primereact/toast',
      'primereact/toolbar',
      'primereact/tooltip',
      'primereact/tree',
    ],
  },
});
