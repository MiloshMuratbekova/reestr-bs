import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Бэкенд работает на 10.10.31.35:8000 в закрытом контуре.
// В разработке запросы /api проксируются туда же.
const BACKEND = process.env.VITE_BACKEND_URL || 'http://10.10.31.35:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
})
