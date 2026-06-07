import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  build: {
    sourcemap: 'hidden'  // hidden-source-map：生成 source map 用于调试，但不在 JS 末尾引用（安全）
  },
  server: {
    host: true,
    port: 3004,
    proxy: {
      '/api/deepseek': {
        target: 'http://localhost:3010',
        changeOrigin: true
      },
      '/api/zhipu': {
        target: 'http://localhost:3010',
        changeOrigin: true
      },
      '/api/v1': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        ws: true
      },
      '/api/v2': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        ws: true
      },
      '/socket.io': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        ws: true
      }
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        // 使用 @use 替代 @import（Sass 3.0 兼容）
        additionalData: `@use "@/styles/mixins.scss" as *;`
      }
    }
  },
  resolve: {
    alias: {
      '@': '/src'
    }
  }
})
