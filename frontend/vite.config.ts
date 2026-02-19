import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          // Isolate heavy charting libraries from app shell boot path.
          if (id.includes('recharts')) {
            return 'vendor-recharts'
          }

          if (id.includes('victory-vendor')) {
            return 'vendor-victory'
          }

          // Auth SDKs are only needed in authenticated route flows.
          if (id.includes('@azure/msal')) {
            return 'vendor-auth'
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/webhook': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
