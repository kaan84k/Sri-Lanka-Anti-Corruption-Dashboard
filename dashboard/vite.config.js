import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api/* to the FastAPI backend on port 8000,
// so the dashboard never needs CORS in development.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
