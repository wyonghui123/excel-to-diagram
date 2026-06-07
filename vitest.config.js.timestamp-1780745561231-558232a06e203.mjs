// vitest.config.js
import { defineConfig } from "file:///D:/filework/excel-to-diagram/node_modules/vitest/dist/config.js";
import vue from "file:///D:/filework/excel-to-diagram/node_modules/@vitejs/plugin-vue/dist/index.mjs";
import { resolve } from "path";
var __vite_injected_original_dirname = "D:\\filework\\excel-to-diagram";
var vitest_config_default = defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: "happy-dom",
    // 比 jsdom 快 2-3 倍
    sourcemap: true,
    // 测试错误指向原始源码
    // 性能优化
    // PR-TestFix-16: 开启测试隔离，根治跨 spec mock 链断裂
    // 单跑 100% 通过 ≠ 全量 100% 通过的根因
    isolate: true,
    // 开启测试隔离（PR-TestFix-16 修复 -30 失败）
    pool: "threads",
    // 线程池
    poolOptions: {
      threads: {
        singleThread: true,
        // 关闭并行调度，避免 worker 间竞态
        isolate: true
        // 与顶层 isolate 一致
      }
    },
    cache: {
      dir: "./node_modules/.cache/vitest"
    },
    include: ["src/**/*.{test,spec}.{js,ts}"],
    exclude: ["node_modules", "dist", "e2e"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*.{js,vue}"],
      exclude: [
        "node_modules/",
        "src/**/*.d.ts",
        "src/**/*.spec.{js,ts}",
        "src/**/*.test.{js,ts}"
      ]
    },
    setupFiles: ["./src/test/setup.js"],
    alias: {
      "@": resolve(__vite_injected_original_dirname, "./src")
    }
  },
  resolve: {
    alias: {
      "@": resolve(__vite_injected_original_dirname, "./src")
    }
  }
});
export {
  vitest_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZXN0LmNvbmZpZy5qcyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiY29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2Rpcm5hbWUgPSBcIkQ6XFxcXGZpbGV3b3JrXFxcXGV4Y2VsLXRvLWRpYWdyYW1cIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkQ6XFxcXGZpbGV3b3JrXFxcXGV4Y2VsLXRvLWRpYWdyYW1cXFxcdml0ZXN0LmNvbmZpZy5qc1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRDovZmlsZXdvcmsvZXhjZWwtdG8tZGlhZ3JhbS92aXRlc3QuY29uZmlnLmpzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZXN0L2NvbmZpZydcbmltcG9ydCB2dWUgZnJvbSAnQHZpdGVqcy9wbHVnaW4tdnVlJ1xuaW1wb3J0IHsgcmVzb2x2ZSB9IGZyb20gJ3BhdGgnXG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFt2dWUoKV0sXG4gIHRlc3Q6IHtcbiAgICBnbG9iYWxzOiB0cnVlLFxuICAgIGVudmlyb25tZW50OiAnaGFwcHktZG9tJywgIC8vIFx1NkJENCBqc2RvbSBcdTVGRUIgMi0zIFx1NTAwRFxuICAgIHNvdXJjZW1hcDogdHJ1ZSwgIC8vIFx1NkQ0Qlx1OEJENVx1OTUxOVx1OEJFRlx1NjMwN1x1NTQxMVx1NTM5Rlx1NTlDQlx1NkU5MFx1NzgwMVxuICAgIC8vIFx1NjAyN1x1ODBGRFx1NEYxOFx1NTMxNlxuICAgIC8vIFBSLVRlc3RGaXgtMTY6IFx1NUYwMFx1NTQyRlx1NkQ0Qlx1OEJENVx1OTY5NFx1NzlCQlx1RkYwQ1x1NjgzOVx1NkNCQlx1OERFOCBzcGVjIG1vY2sgXHU5NEZFXHU2NUFEXHU4OEMyXG4gICAgLy8gXHU1MzU1XHU4REQxIDEwMCUgXHU5MDFBXHU4RkM3IFx1MjI2MCBcdTUxNjhcdTkxQ0YgMTAwJSBcdTkwMUFcdThGQzdcdTc2ODRcdTY4MzlcdTU2RTBcbiAgICBpc29sYXRlOiB0cnVlLCAgLy8gXHU1RjAwXHU1NDJGXHU2RDRCXHU4QkQ1XHU5Njk0XHU3OUJCXHVGRjA4UFItVGVzdEZpeC0xNiBcdTRGRUVcdTU5MEQgLTMwIFx1NTkzMVx1OEQyNVx1RkYwOVxuICAgIHBvb2w6ICd0aHJlYWRzJywgIC8vIFx1N0VCRlx1N0EwQlx1NkM2MFxuICAgIHBvb2xPcHRpb25zOiB7XG4gICAgICB0aHJlYWRzOiB7XG4gICAgICAgIHNpbmdsZVRocmVhZDogdHJ1ZSwgIC8vIFx1NTE3M1x1OTVFRFx1NUU3Nlx1ODg0Q1x1OEMwM1x1NUVBNlx1RkYwQ1x1OTA3Rlx1NTE0RCB3b3JrZXIgXHU5NUY0XHU3QURFXHU2MDAxXG4gICAgICAgIGlzb2xhdGU6IHRydWUsICAvLyBcdTRFMEVcdTk4NzZcdTVDNDIgaXNvbGF0ZSBcdTRFMDBcdTgxRjRcbiAgICAgIH1cbiAgICB9LFxuICAgIGNhY2hlOiB7XG4gICAgICBkaXI6ICcuL25vZGVfbW9kdWxlcy8uY2FjaGUvdml0ZXN0JyxcbiAgICB9LFxuICAgIGluY2x1ZGU6IFsnc3JjLyoqLyoue3Rlc3Qsc3BlY30ue2pzLHRzfSddLFxuICAgIGV4Y2x1ZGU6IFsnbm9kZV9tb2R1bGVzJywgJ2Rpc3QnLCAnZTJlJ10sXG4gICAgY292ZXJhZ2U6IHtcbiAgICAgIHByb3ZpZGVyOiAndjgnLFxuICAgICAgcmVwb3J0ZXI6IFsndGV4dCcsICdqc29uJywgJ2h0bWwnXSxcbiAgICAgIGluY2x1ZGU6IFsnc3JjLyoqLyoue2pzLHZ1ZX0nXSxcbiAgICAgIGV4Y2x1ZGU6IFtcbiAgICAgICAgJ25vZGVfbW9kdWxlcy8nLFxuICAgICAgICAnc3JjLyoqLyouZC50cycsXG4gICAgICAgICdzcmMvKiovKi5zcGVjLntqcyx0c30nLFxuICAgICAgICAnc3JjLyoqLyoudGVzdC57anMsdHN9J1xuICAgICAgXVxuICAgIH0sXG4gICAgc2V0dXBGaWxlczogWycuL3NyYy90ZXN0L3NldHVwLmpzJ10sXG4gICAgYWxpYXM6IHtcbiAgICAgICdAJzogcmVzb2x2ZShfX2Rpcm5hbWUsICcuL3NyYycpXG4gICAgfVxuICB9LFxuICByZXNvbHZlOiB7XG4gICAgYWxpYXM6IHtcbiAgICAgICdAJzogcmVzb2x2ZShfX2Rpcm5hbWUsICcuL3NyYycpXG4gICAgfVxuICB9XG59KVxuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUFnUixTQUFTLG9CQUFvQjtBQUM3UyxPQUFPLFNBQVM7QUFDaEIsU0FBUyxlQUFlO0FBRnhCLElBQU0sbUNBQW1DO0FBSXpDLElBQU8sd0JBQVEsYUFBYTtBQUFBLEVBQzFCLFNBQVMsQ0FBQyxJQUFJLENBQUM7QUFBQSxFQUNmLE1BQU07QUFBQSxJQUNKLFNBQVM7QUFBQSxJQUNULGFBQWE7QUFBQTtBQUFBLElBQ2IsV0FBVztBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUEsSUFJWCxTQUFTO0FBQUE7QUFBQSxJQUNULE1BQU07QUFBQTtBQUFBLElBQ04sYUFBYTtBQUFBLE1BQ1gsU0FBUztBQUFBLFFBQ1AsY0FBYztBQUFBO0FBQUEsUUFDZCxTQUFTO0FBQUE7QUFBQSxNQUNYO0FBQUEsSUFDRjtBQUFBLElBQ0EsT0FBTztBQUFBLE1BQ0wsS0FBSztBQUFBLElBQ1A7QUFBQSxJQUNBLFNBQVMsQ0FBQyw4QkFBOEI7QUFBQSxJQUN4QyxTQUFTLENBQUMsZ0JBQWdCLFFBQVEsS0FBSztBQUFBLElBQ3ZDLFVBQVU7QUFBQSxNQUNSLFVBQVU7QUFBQSxNQUNWLFVBQVUsQ0FBQyxRQUFRLFFBQVEsTUFBTTtBQUFBLE1BQ2pDLFNBQVMsQ0FBQyxtQkFBbUI7QUFBQSxNQUM3QixTQUFTO0FBQUEsUUFDUDtBQUFBLFFBQ0E7QUFBQSxRQUNBO0FBQUEsUUFDQTtBQUFBLE1BQ0Y7QUFBQSxJQUNGO0FBQUEsSUFDQSxZQUFZLENBQUMscUJBQXFCO0FBQUEsSUFDbEMsT0FBTztBQUFBLE1BQ0wsS0FBSyxRQUFRLGtDQUFXLE9BQU87QUFBQSxJQUNqQztBQUFBLEVBQ0Y7QUFBQSxFQUNBLFNBQVM7QUFBQSxJQUNQLE9BQU87QUFBQSxNQUNMLEtBQUssUUFBUSxrQ0FBVyxPQUFPO0FBQUEsSUFDakM7QUFBQSxFQUNGO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
