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
    isolate: false,
    // 关闭测试隔离（单元测试）
    pool: "threads",
    // 线程池
    poolOptions: {
      threads: {
        singleThread: false,
        isolate: false
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
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZXN0LmNvbmZpZy5qcyJdLAogICJzb3VyY2VzQ29udGVudCI6IFsiY29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2Rpcm5hbWUgPSBcIkQ6XFxcXGZpbGV3b3JrXFxcXGV4Y2VsLXRvLWRpYWdyYW1cIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfZmlsZW5hbWUgPSBcIkQ6XFxcXGZpbGV3b3JrXFxcXGV4Y2VsLXRvLWRpYWdyYW1cXFxcdml0ZXN0LmNvbmZpZy5qc1wiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9pbXBvcnRfbWV0YV91cmwgPSBcImZpbGU6Ly8vRDovZmlsZXdvcmsvZXhjZWwtdG8tZGlhZ3JhbS92aXRlc3QuY29uZmlnLmpzXCI7aW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSAndml0ZXN0L2NvbmZpZydcbmltcG9ydCB2dWUgZnJvbSAnQHZpdGVqcy9wbHVnaW4tdnVlJ1xuaW1wb3J0IHsgcmVzb2x2ZSB9IGZyb20gJ3BhdGgnXG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFt2dWUoKV0sXG4gIHRlc3Q6IHtcbiAgICBnbG9iYWxzOiB0cnVlLFxuICAgIGVudmlyb25tZW50OiAnaGFwcHktZG9tJywgIC8vIFx1NkJENCBqc2RvbSBcdTVGRUIgMi0zIFx1NTAwRFxuICAgIHNvdXJjZW1hcDogdHJ1ZSwgIC8vIFx1NkQ0Qlx1OEJENVx1OTUxOVx1OEJFRlx1NjMwN1x1NTQxMVx1NTM5Rlx1NTlDQlx1NkU5MFx1NzgwMVxuICAgIC8vIFx1NjAyN1x1ODBGRFx1NEYxOFx1NTMxNlxuICAgIGlzb2xhdGU6IGZhbHNlLCAgLy8gXHU1MTczXHU5NUVEXHU2RDRCXHU4QkQ1XHU5Njk0XHU3OUJCXHVGRjA4XHU1MzU1XHU1MTQzXHU2RDRCXHU4QkQ1XHVGRjA5XG4gICAgcG9vbDogJ3RocmVhZHMnLCAgLy8gXHU3RUJGXHU3QTBCXHU2QzYwXG4gICAgcG9vbE9wdGlvbnM6IHtcbiAgICAgIHRocmVhZHM6IHtcbiAgICAgICAgc2luZ2xlVGhyZWFkOiBmYWxzZSxcbiAgICAgICAgaXNvbGF0ZTogZmFsc2UsXG4gICAgICB9XG4gICAgfSxcbiAgICBjYWNoZToge1xuICAgICAgZGlyOiAnLi9ub2RlX21vZHVsZXMvLmNhY2hlL3ZpdGVzdCcsXG4gICAgfSxcbiAgICBpbmNsdWRlOiBbJ3NyYy8qKi8qLnt0ZXN0LHNwZWN9Lntqcyx0c30nXSxcbiAgICBleGNsdWRlOiBbJ25vZGVfbW9kdWxlcycsICdkaXN0JywgJ2UyZSddLFxuICAgIGNvdmVyYWdlOiB7XG4gICAgICBwcm92aWRlcjogJ3Y4JyxcbiAgICAgIHJlcG9ydGVyOiBbJ3RleHQnLCAnanNvbicsICdodG1sJ10sXG4gICAgICBpbmNsdWRlOiBbJ3NyYy8qKi8qLntqcyx2dWV9J10sXG4gICAgICBleGNsdWRlOiBbXG4gICAgICAgICdub2RlX21vZHVsZXMvJyxcbiAgICAgICAgJ3NyYy8qKi8qLmQudHMnLFxuICAgICAgICAnc3JjLyoqLyouc3BlYy57anMsdHN9JyxcbiAgICAgICAgJ3NyYy8qKi8qLnRlc3Que2pzLHRzfSdcbiAgICAgIF1cbiAgICB9LFxuICAgIHNldHVwRmlsZXM6IFsnLi9zcmMvdGVzdC9zZXR1cC5qcyddLFxuICAgIGFsaWFzOiB7XG4gICAgICAnQCc6IHJlc29sdmUoX19kaXJuYW1lLCAnLi9zcmMnKVxuICAgIH1cbiAgfSxcbiAgcmVzb2x2ZToge1xuICAgIGFsaWFzOiB7XG4gICAgICAnQCc6IHJlc29sdmUoX19kaXJuYW1lLCAnLi9zcmMnKVxuICAgIH1cbiAgfVxufSlcbiJdLAogICJtYXBwaW5ncyI6ICI7QUFBZ1IsU0FBUyxvQkFBb0I7QUFDN1MsT0FBTyxTQUFTO0FBQ2hCLFNBQVMsZUFBZTtBQUZ4QixJQUFNLG1DQUFtQztBQUl6QyxJQUFPLHdCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsSUFBSSxDQUFDO0FBQUEsRUFDZixNQUFNO0FBQUEsSUFDSixTQUFTO0FBQUEsSUFDVCxhQUFhO0FBQUE7QUFBQSxJQUNiLFdBQVc7QUFBQTtBQUFBO0FBQUEsSUFFWCxTQUFTO0FBQUE7QUFBQSxJQUNULE1BQU07QUFBQTtBQUFBLElBQ04sYUFBYTtBQUFBLE1BQ1gsU0FBUztBQUFBLFFBQ1AsY0FBYztBQUFBLFFBQ2QsU0FBUztBQUFBLE1BQ1g7QUFBQSxJQUNGO0FBQUEsSUFDQSxPQUFPO0FBQUEsTUFDTCxLQUFLO0FBQUEsSUFDUDtBQUFBLElBQ0EsU0FBUyxDQUFDLDhCQUE4QjtBQUFBLElBQ3hDLFNBQVMsQ0FBQyxnQkFBZ0IsUUFBUSxLQUFLO0FBQUEsSUFDdkMsVUFBVTtBQUFBLE1BQ1IsVUFBVTtBQUFBLE1BQ1YsVUFBVSxDQUFDLFFBQVEsUUFBUSxNQUFNO0FBQUEsTUFDakMsU0FBUyxDQUFDLG1CQUFtQjtBQUFBLE1BQzdCLFNBQVM7QUFBQSxRQUNQO0FBQUEsUUFDQTtBQUFBLFFBQ0E7QUFBQSxRQUNBO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxJQUNBLFlBQVksQ0FBQyxxQkFBcUI7QUFBQSxJQUNsQyxPQUFPO0FBQUEsTUFDTCxLQUFLLFFBQVEsa0NBQVcsT0FBTztBQUFBLElBQ2pDO0FBQUEsRUFDRjtBQUFBLEVBQ0EsU0FBUztBQUFBLElBQ1AsT0FBTztBQUFBLE1BQ0wsS0FBSyxRQUFRLGtDQUFXLE9BQU87QUFBQSxJQUNqQztBQUFBLEVBQ0Y7QUFDRixDQUFDOyIsCiAgIm5hbWVzIjogW10KfQo=
