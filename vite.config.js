import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { visualizer } from 'rollup-plugin-visualizer'

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
    // [FR-018] Bundle 分析工具: npm run analyze 生成 stats.html
    visualizer({
      open: false,
      gzipSize: true,
      brotliSize: true,
      filename: 'stats.html',
    }),
  ],
  build: {
    sourcemap: 'hidden',  // hidden-source-map：生成 source map 用于调试，但不在 JS 末尾引用（安全）
    // [FR-002] 分包策略: 将大型依赖拆分为独立 chunk, 优化首屏加载和缓存命中率
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Vue + EP + @vueuse 合并 (避免循环依赖: EP 依赖 @vueuse, @vueuse 依赖 vue)
            if (id.includes('/vue/') || id.includes('/vue-router/') || id.includes('/pinia/') || id.includes('pinia-plugin-persistedstate') || id.includes('/element-plus/') || id.includes('@element-plus/') || id.includes('@vueuse/')) {
              return 'vendor-vue-ep'
            }
            // ECharts
            if (id.includes('/echarts/') || id.includes('/zrender/')) {
              return 'vendor-echarts'
            }
            // Mermaid + 全部子依赖 + misc (mermaid 与 misc 有循环依赖, 合并)
            if (id.includes('/mermaid/') || id.includes('/@mermaid-js/') || id.includes('/d3-') || id.includes('/dagre') || id.includes('/elkjs/') || id.includes('/katex/') || id.includes('/web-worker/') || id.includes('/stylis/') || id.includes('/cytoscape')) {
              return 'vendor-mermaid'
            }
            // XLSX
            if (id.includes('/xlsx/') || id.includes('/codepage/')) {
              return 'vendor-xlsx'
            }
            // PDF 导出
            if (id.includes('/html2canvas/') || id.includes('/jspdf/') || id.includes('/canvg/')) {
              return 'vendor-pdf'
            }
            // 其他第三方库 (与 mermaid 合并, 避免循环)
            return 'vendor-mermaid'
          }
        }
      }
    }
  },
  server: {
    host: true,
    port: 3004,
    proxy: {
      // [FR-009] 合并所有 /api/* 到统一代理规则 (原来 5 条独立规则, target 相同)
      '/api': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        ws: true,
        timeout: 30000,       // 代理请求超时 30s (大文件上传等)
        proxyTimeout: 30000,  // 后端响应超时 30s
        configure: (proxy) => {
          proxy.on('error', (err) => {
            // 代理连接错误日志 (不阻塞,仅输出)
            // eslint-disable-next-line no-console
            console.error('[Vite Proxy] Connection error:', err.message)
          })
        }
      },
      '/socket.io': {
        target: 'http://localhost:3010',
        changeOrigin: true,
        ws: true,
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
