---
alwaysApply: false
description: "Vitest 调试 + 性能优化 + 完整配置 + 检查清单"
---

# Vitest 调试 + 性能（v4.0 拆分）

> **拆分自** `frontend-testing-standards.md` (583 行)
> **本文件覆盖**：§5 定位问题 + §6 性能优化 + §7 配置 + §8 检查清单 + §9 工具链
> **相关**：[vitest-setup.md](./vitest-setup.md)（工具选型 + 容易测试）

---

## 5. 容易定位问题的实践

### 5.1 Source Map 配置

```javascript
// vite.config.js
export default defineConfig({
  build: {
    sourcemap: true  // 关键：失败堆栈指向原文件
  }
})
```

### 5.2 错误堆栈格式化

```javascript
// vitest.config.js
export default defineConfig({
  test: {
    onConsoleLog: () => false,
    outputDiffMaxSize: 4096
  }
})
```

### 5.3 @vitest/ui 可视化调试

```bash
# 启动 UI 模式
npx vitest --ui

# 访问 http://localhost:51204/__vitest__/
```

### 5.4 Vue DevTools 启用

```javascript
// vite.config.js
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue({
    template: {
      transformAssetUrls: {
        base: null,
        includeAbsolute: false
      }
    }
  })]
})
```

---

## 6. 性能优化实践

### 6.1 升级 happy-dom（vs jsdom）

| 维度 | jsdom | happy-dom |
|------|-------|-----------|
| 启动速度 | 慢 | **快 5-10x** |
| 内存 | 大 | 小 |
| 兼容性 | 完整 | 99% |

迁移：
```javascript
// vitest.config.js
export default defineConfig({
  test: {
    environment: 'happy-dom'  // 不是 jsdom
  }
})
```

### 6.2 智能缓存

```javascript
test: {
  cache: {
    dir: './node_modules/.vitest'
  }
}
```

### 6.3 智能并行

```bash
# 跑全部测试，4 个 worker 并行
npx vitest run --reporter=verbose

# 跑单个测试
npx vitest run path/to/test.spec.js
```

### 6.4 测试分层运行

```bash
# 单元测试（快速反馈）
npm run test:unit

# 集成测试（核心覆盖）
npm run test:integration

# 全部测试（CI）
npm run test:all
```

---

## 7. 完整的最佳实践配置

### 7.1 package.json

```json
{
  "scripts": {
    "test:unit": "vitest run --dir tests/unit",
    "test:integration": "vitest run --dir tests/integration",
    "test:all": "vitest run",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest run --coverage"
  },
  "devDependencies": {
    "vitest": "^1.0.0",
    "happy-dom": "^12.0.0",
    "@vitest/ui": "^1.0.0",
    "msw": "^2.0.0",
    "@testing-library/vue": "^8.0.0"
  }
}
```

### 7.2 推荐的测试文件结构

```
tests/
├── unit/                  # 单元测试
│   ├── components/
│   └── utils/
├── integration/           # 集成测试
│   ├── api/
│   └── flows/
├── e2e/                   # E2E（Playwright）
├── factories/             # 数据工厂
├── fixtures/              # 共享 fixture
└── setup.js               # 全局 setup
```

---

## 8. 检查清单

### 写测试前
- [ ] 是否已有类似测试（避免重复）
- [ ] 测试层级（unit / integration / e2e）
- [ ] mock 是否需要（MSW vs 真实调用）

### 写测试时
- [ ] `beforeEach` 初始化 wrapper / store
- [ ] 测试用例独立（不依赖顺序）
- [ ] 断言具体值而非 truthy
- [ ] 错误情况覆盖

### 写测试后
- [ ] 跑测试确认通过
- [ ] 检查覆盖率
- [ ] 跑全量测试确认无破坏
- [ ] 提交前跑一次

---

## 9. 工具链总结

| 工具 | 版本 | 用途 |
|------|------|------|
| Vitest | 1.x+ | 测试运行器 |
| happy-dom | 12.x+ | DOM 环境 |
| MSW | 2.x+ | API mock |
| @vitest/ui | 1.x+ | 可视化调试 |
| @testing-library/vue | 8.x+ | Vue 测试工具 |
| @vitest/coverage-v8 | 1.x+ | 覆盖率 |

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 frontend-testing-standards 拆出 |