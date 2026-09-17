import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { visualizer } from 'rollup-plugin-visualizer'
import { readFileSync } from 'fs'

// [P0 2026-09-05 端口单一真源] 默认端口统一读 scripts/ports.json,
//   进程环境变量仍可覆盖 (多实例场景)。历史兜底 3010/3005 已删除。
const PORTS = JSON.parse(readFileSync(new URL('./scripts/ports.json', import.meta.url)))

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // [FIX 2026-07-23-R16] 用 loadEnv 加载 .env (非端口变量仍可用)
  const env = loadEnv(mode, process.cwd(), '')
  const backendPort = process.env.BACKEND_PORT || String(PORTS.backend)

return {
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
    // [FR-018] Bundle 分析工具: npm run analyze 生成 stats.html
    // [FIX 2026-09-12] 无条件注册导致常规 build 在 gzip/brotli 统计时 zlib OOM
    //   (rendering chunks 阶段 [visualizer] insufficient memory)。按原意改为
    //   --mode analyze 按需启用, 常规 build 不再付出内存代价
    ...(mode === 'analyze' ? [visualizer({
      open: false,
      gzipSize: true,
      brotliSize: true,
      filename: 'stats.html',
    })] : []),
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
            // [FIX 2026-09-03] 取消独立 vendor-pdf 桶, 并入 vendor-mermaid (默认桶)
            // 根因: jspdf 的可选依赖 dompurify 被安装后 (fe94803), jspdf(vendor-pdf) → dompurify(默认桶
            //       vendor-mermaid) 的 import 边激活, 与 vendor-mermaid → vendor-pdf 的边构成双向循环;
            //       ES module 循环初始化时 canvg PathParser 的基类绑定未就绪 →
            //       "Class extends value undefined is not a constructor" (staging 18081 实锤)。
            // 8/31 构建时 dompurify 不在 node_modules, 该边不存在, 故旧 dist 正常。
            // html2canvas/jspdf/canvg 及其可选子依赖 (dompurify/fflate 等) 全部同桶, 循环消失。
            // if (id.includes('/html2canvas/') || id.includes('/jspdf/') || id.includes('/canvg/')) {
            //   return 'vendor-pdf'
            // }
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
    // [P0 2026-09-05] 默认读 scripts/ports.json (3006), VITE_PORT 环境变量可覆盖
    port: parseInt(process.env.VITE_PORT || String(PORTS.frontend), 10),
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
    // [FIX BUG-V032 2026-09-03] 修复 localhost:3005 响应解析失败 (status=500)
    // 根因: Node v24 + chokidar 在 lstat 已删除的 cookies_qa.txt (gitignore 残留)
    //       时抛 UNKNOWN error (errno=-4094), chokidar FSWatcher 上抛 unhandled error,
    //       整个 vite 进程被 kill, 端口被 zombie 占用, 后续请求返回 500。
    // 复现: 任意时刻删掉 cookies_*.txt 都会触发; 已记入 .runtime/vite_3006.err:308-326
    // 修复: server.watch.ignored 排除所有 .gitignore 残留文件 + 运行时产物
    watch: {
      ignored: [
        // .gitignore 通配符残留 (运行时被创建又删除, 导致 chokidar lstat 报错)
        '**/cookies_*.txt',
        '**/cookies.txt',
        // SQLite 运行时文件 (gitignore .*.db-wal 等, chokidar 持续轮询会卡顿)
        '**/*.db',
        '**/*.db-wal',
        '**/*.db-shm',
        // 服务管理器状态文件 (高频写, 无意义监听)
        '**/.service_manager.lock',
        '**/.service_status*.json',
        '**/*.pid',
        // 部署产物 / 临时目录
        '**/frontend_dist_files/**',
        '**/.runtime/**',
        '**/.tmp/**',
        '**/_archive_*/**',
        '**/deploy-v*.zip',
        // Vite 自身产物 (避免 self-watch 触发 reload 循环)
        '**/dist/**',
        '**/node_modules/**',
        '**/.vite/**',
        '**/stats.html',
        // 日志 (高频写入, 不需要 HMR)
        '**/*.log',
        '**/logs/**',
      ],
    },
    proxy: {
      // [v3.3] 动态代理: 支持多 Agent worktree 自验证
      // 默认代理到 3004 (主仓库后端), Agent 通过 BACKEND_PORT 环境变量覆盖
      // [FIX BUG-V031 2026-08-28] localhost → 127.0.0.1
      //   原因: Node.js 24 默认把 `localhost` 解析为 IPv6 `::1`,
      //         后端 waitress 只绑 IPv4, proxy 连 `::1:3010` 被拒后 vite 包装为 500
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
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
        target: `http://127.0.0.1:${backendPort}`,
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
}
})
