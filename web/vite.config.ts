import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy sang backend FastAPI để frontend gọi '/api/...' mà không vướng CORS.
// usePolling: repo nằm trên /mnt/d (filesystem 9p của WSL) — HMR mặc định KHÔNG thấy
// file thay đổi, buộc phải polling thì sửa code mới tự reload.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    watch: { usePolling: true, interval: 300 },
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
