import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',  // 比 jsdom 快 2-3 倍
    sourcemap: true,  // 测试错误指向原始源码
    // 性能优化
    // PR-TestFix-16: 开启测试隔离，根治跨 spec mock 链断裂
    // 单跑 100% 通过 ≠ 全量 100% 通过的根因
    isolate: true,  // 开启测试隔离（PR-TestFix-16 修复 -30 失败）
    pool: 'threads',  // 线程池
    poolOptions: {
      threads: {
        singleThread: true,  // 关闭并行调度，避免 worker 间竞态
        isolate: true,  // 与顶层 isolate 一致
      }
    },
    cache: {
      dir: './node_modules/.cache/vitest',
    },
    include: ['src/**/*.{test,spec}.{js,ts}', 'e2e/screenplay/**/*.{test,spec}.{js,ts}'],
    exclude: ['node_modules', 'dist', 'e2e/features', 'e2e/smoke', 'e2e/specs'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{js,vue}'],
      exclude: [
        'node_modules/',
        'src/**/*.d.ts',
        'src/**/*.spec.{js,ts}',
        'src/**/*.test.{js,ts}'
      ]
    },
    setupFiles: ['./src/test/setup.js'],
    alias: {
      '@': resolve(__dirname, './src')
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src')
    }
  }
})
