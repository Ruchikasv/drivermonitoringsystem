import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/sessions': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/owner': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/incidents': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/vehicles': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/drivers': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/trips': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/alerts': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/analytics': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/alcohol': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  }
})
