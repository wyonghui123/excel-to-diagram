import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3004,
    proxy: {
      '/api/deepseek': {
        target: 'http://localhost:3001',
        changeOrigin: true
      },
      '/api/zhipu': {
        target: 'http://localhost:3001',
        changeOrigin: true
      }
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `
          @import "@/styles/variables.scss";
          @import "@/styles/mixins.scss";
        `
      }
    }
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  }
})