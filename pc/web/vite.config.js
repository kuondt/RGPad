import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// npm run dev: giao dien o cong 5173, goi /api sang backend Python (rgpad_web.py)
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8740' },
  },
})
