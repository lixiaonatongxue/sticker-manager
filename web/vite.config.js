import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式：vite 起在 5173，/api 代理到本地 FastAPI（8765）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
