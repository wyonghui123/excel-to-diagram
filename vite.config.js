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
            // [FIX 2026-08-18] PDF 导出依赖 (html2canvas/jspdf/canvg) 不再单独分包:
            //   之前独立 vendor-pdf chunk 与 vendor-mermaid 形成循环依赖
            //   (mermaid 为 PNG 导出 import canvg, canvg import d3/其他 mermaid 依赖),
            //   Rollup 报 "Circular chunk: vendor-pdf -> vendor-mermaid -> vendor-pdf",
            //   运行时 vendor-pdf 内 `class X extends _a` (extends 自 vendor-mermaid)
            //   因 ESM 循环初始化顺序抛 "Class extends value undefined" → 整个前端无法挂载
            //   (v20260817 起已受影响, 仅靠 HTTP 200 校验未发现).
            //   修复: 让 pdf 依赖落到下方默认 vendor-mermaid 桶, 消除跨 chunk 循环.
            //   代价: 首屏多加载 ~0.6MB (pdf 导出库), 换取构建可运行.
            // 其他第三方库 (与 mermaid 合并, 避免循环)
            return 'vendor-mermaid'
          }
        }
      }
    }
  },
  server: {
    host: true,
    // [v3.3] 动态端口: 支持多 Agent worktree 自验证
    // 默认 3005 (主仓库), Agent 通过 VITE_PORT 环境变量覆盖
    port: parseInt(process.env.VITE_PORT || '3005', 10),
    // [FIX 2026-08-09 防重复实例] 端口被占时直接启动失败, 而非 Vite 默认静默落到下一个端口.
    //   根因: service_manager 用 --port 3004, npm run dev 用 config 默认 3005, 两入口端口不一致
    //   → 可同时并存互不冲突 → 两个 vite 抢 CPU 拖慢登录后页面.
    //   strictPort 只对"同端口重复启动"生效, 各 Agent 用不同 VITE_PORT 时不受影响 (兼容多 Agent worktree).
    strictPort: true,
    // [FIX 2026-06-12 #13] 根治 MetaListPage toolbar/table "又这样了" 复发
    // 根因: 浏览器缓存 Vite 编译产物 (SCSS 改完后旧 CSS 被缓存)
    // 用户反馈"我刷新后现在又好了" 确认是缓存问题
    // 修复: dev server 返回 no-store 头, 强制浏览器每次重新拉资源
    // 范围: dev 模式生效 (server.headers), production 由 Vite 静态资源 hash 控制
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0',
    },
    hmr: {
      // [Node.js 24 兼容] 使用 polling 模式替代 WebSocket：
      // Vite 6.4.1 的 WS HMR 服务器在 Node.js 24.14.0 上挂死，
      // 导致浏览器控制台持续报错。改用 polling 后浏览器通过 HTTP 长轮询
      // 接收文件变化通知，功能完全正常。
      protocol: 'ws',
      overlay: true,
      timeout: 30000,
    },
    proxy: {
      // [v3.3] 动态代理: 支持多 Agent worktree 自验证
      // 默认代理到 3004 (主仓库后端), Agent 通过 BACKEND_PORT 环境变量覆盖
      '/api': {
        // [PERF 2026-08-15] target 用 127.0.0.1 而非 localhost:
        //   localhost 优先解析 IPv6 (::1), 而 waitress 只监听 IPv4 (0.0.0.0),
        //   每次代理新建连接先尝试 ::1 超时 ~2s 再回退 127.0.0.1,
        //   导致前端所有 API 请求慢 2s (初始加载累积 40s+).
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || '3010'}`,
        changeOrigin: true,
        ws: true,
        // [FIX BUG-V029 2026-06-28] 30s→180s
        //   原因: Excel 导入预检测对 1.34MB / 23839 行文件需 63.7s,
        //         30s proxy 超时强制断连导致前端报 ERR_EMPTY_RESPONSE
        //   验证: 直连 3010 63.7s 成功, 经 3004 proxy 30.0s 报 RemoteDisconnected
        //   选值: 180s (3 min) 留 2-3x headroom, 仍能在挂死时及时终止
        timeout: 180000,      // 代理请求超时 180s (大文件上传 / Excel 导入预检测)
        proxyTimeout: 180000, // 后端响应超时 180s
        configure: (proxy) => {
          proxy.on('error', (err) => {
            // 代理连接错误日志 (不阻塞,仅输出)
            // eslint-disable-next-line no-console
            console.error('[Vite Proxy] Connection error:', err.message)
          })
        }
      },
      '/socket.io': {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || '3010'}`,
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
