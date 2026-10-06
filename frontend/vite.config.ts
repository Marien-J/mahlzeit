/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// The API runs on :8000 during development (`uv run uvicorn ...`); Caddy does this in production.
const apiTarget = process.env.API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectRegister: false,
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest,woff2}'],
      },
      manifest: {
        name: 'Mahlzeit',
        lang: 'de',
        short_name: 'Mahlzeit',
        description: 'Plan meals, shop, track food and training together.',
        id: '/',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f7f5f0',
        theme_color: '#2f6b4f',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173,
    proxy: { '/api': apiTarget, '/events': apiTarget, '/mcp': apiTarget },
  },
  build: { target: 'es2022', sourcemap: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
