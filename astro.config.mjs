import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import AstroPWA from '@vite-pwa/astro';

export default defineConfig({
  integrations: [
    AstroPWA({
      registerType: 'autoUpdate',
      includeAssets: [
        'favicon.ico',
        'favicon-180x180.png',
        'favicon-192x192.png',
        'favicon-512x512.png',
      ],
      manifest: {
        name: 'Maoty',
        short_name: 'Maoty',
        description: 'Maoty homepage',
        start_url: '/',
        display: 'standalone',
        background_color: '#fffbeb',
        theme_color: '#fffbeb',
        icons: [
          {
            src: 'favicon-180x180.png',
            sizes: '180x180',
            type: 'image/png',
          },
          {
            src: 'favicon-192x192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'favicon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: 'favicon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{css,js,html,svg,png,ico,webp,woff2}'],
        navigateFallback: '/',
      },
      devOptions: {
        enabled: true,
        navigateFallbackAllowlist: [/^\/$/],
      },
    }),
  ],
  server: {
    host: true,
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
