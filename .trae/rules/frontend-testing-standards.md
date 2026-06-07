# 前端测试标准规范

> **目标：让前端测试容易编写、容易定位问题、性能优秀。**

## 三大原则

| 原则 | 说明 | 工具 |
|------|------|------|
| **容易测试** | 测试模板化、减少 setup、复用 fixture | MSW + 工厂模式 |
| **容易定位** | Source Map + Vue DevTools + 详细错误 | Vite sourcemap + DevTools |
| **性能优秀** | happy-dom + 并行 + 缓存 | Vitest 配置优化 |

---

## 1. 工具选型（2026 最佳实践）

### [OK] 推荐配置

| 工具 | 版本 | 作用 | 为什么 |
|------|------|------|--------|
| **Vitest** | 2.1+ | 单元/组件测试 | 市场份额 45%（2026），Vite 原生支持 |
| **@vue/test-utils** | 2.4+ | Vue 组件测试 | Vue 官方工具 |
| **happy-dom** | 15+ | DOM 模拟 | 比 jsdom 快 2-3 倍 |
| **@vitest/ui** | 2.1+ | 调试 UI | 可视化测试运行 |
| **MSW** | 2+ | API mocking | Service Worker 拦截，更真实 |
| **@playwright/test** | 1.60+ | E2E 测试 | 已经是项目选择 |

### [X] 避免的反模式

| 反模式 | 原因 |
|--------|------|
| 直接用 `axios.get('/api/...')` 测试 | 难以控制返回值，无法模拟错误 |
| 用 jsdom | 比 happy-dom 慢 2-3 倍 |
| 测试中 sleep 等待 | 不可靠，应该用 `waitFor` |
| 一次性写超长测试 | 应该拆分，单个测试 < 1 秒 |

---

## 2. 项目当前问题分析

### 问题 1：Source Map 未开启

**症状**：测试失败时，错误信息指向压缩后的代码（`app.[hash].js`），无法定位源码位置。

**影响**：
- 错误信息：`at app.abc123.js:1:2345`
- 而不是：`at src/components/UserCard.vue:42:5`
- 调试时无法直接定位问题

**修复**：

```js
// vite.config.js
export default defineConfig({
  build: {
    sourcemap: true,  // 开启 Source Map
  },
  // 测试环境配置
  test: {
    environment: 'happy-dom',  // 比 jsdom 快 2-3 倍
    sourcemap: true,  // 测试也生成 source map
  }
})
```

### 问题 2：jsdom 性能问题

**对比**：

| 模拟器 | 启动时间 | 内存占用 | 兼容性 |
|--------|---------|---------|--------|
| **jsdom** | 1.5s | 高（~200MB） | 100% |
| **happy-dom** | 0.5s | 低（~50MB） | 95% |
| **真实浏览器** | - | - | 100% |

**推荐**：
- 默认用 happy-dom（快）
- 特殊需求（如 Web Audio）用 jsdom

### 问题 3：API Mock 不规范

**错误做法**：
```js
// [X] 错误：直接 mock 模块
vi.mock('@/api/user', () => ({
  getUser: vi.fn().mockResolvedValue({ id: 1, name: 'Test' })
}))

test('should display user', async () => {
  const wrapper = mount(UserCard)
  // 模块已 mock，但其他测试可能也需要 mock
})
```

**正确做法**（用 MSW）：
```js
// [OK] 正确：用 MSW 拦截 fetch
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

const server = setupServer(
  http.get('/api/v2/user/1', () => {
    return HttpResponse.json({ id: 1, name: 'Test User' })
  })
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('should display user', async () => {
  const wrapper = mount(UserCard, { props: { userId: 1 } })
  await flushPromises()
  expect(wrapper.text()).toContain('Test User')
})
```

**优势**：
- 真实拦截网络层
- 测试代码不需要改业务代码
- 容易模拟错误（500、超时）
- 与 E2E 测试一致

---

## 3. 测试金字塔（性能分层）

### 比例建议

```
       /\
      /E2E\         10%（10-20 个测试，5-10 分钟）
     /------\
    / 组件  \       20%（50-100 个测试，1-3 分钟）
   /----------\
  / 单元测试  \    70%（200-500 个测试，< 1 分钟）
 /--------------\
```

**性能对比**：

| 测试类型 | 数量 | 单个耗时 | 总耗时 | 反馈速度 |
|---------|------|---------|--------|---------|
| 单元测试 | 200 | 5ms | 1s | 极快 |
| 组件测试 | 50 | 100ms | 5s | 快 |
| E2E 测试 | 10 | 30s | 5m | 慢 |

**策略**：
- 改完代码：跑单元测试（< 1 分钟）
- 提交前：跑单元 + 组件（< 5 分钟）
- 发布前：跑全套（< 10 分钟）

---

## 4. 容易测试的实践

### 4.1 测试模板

**每个组件测试文件**：

```js
// src/components/UserCard.spec.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import UserCard from './UserCard.vue'

// 1. 公共 setup
function createWrapper(props = {}, options = {}) {
  return mount(UserCard, {
    props: { userId: 1, ...props },
    global: {
      plugins: [createPinia(), createI18n({ legacy: false })],
      stubs: { ElIcon: true, ElButton: true },
      ...options.global
    },
    ...options
  })
}

describe('UserCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  // 2. 渲染测试
  describe('rendering', () => {
    it('should render user name', () => {
      const wrapper = createWrapper({ user: { id: 1, name: 'John' } })
      expect(wrapper.text()).toContain('John')
    })
  })

  // 3. 交互测试
  describe('interactions', () => {
    it('should emit click event', async () => {
      const wrapper = createWrapper()
      await wrapper.find('button').trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
    })
  })

  // 4. 边界情况
  describe('edge cases', () => {
    it('should handle empty user', () => {
      const wrapper = createWrapper({ user: null })
      expect(wrapper.find('.empty').exists()).toBe(true)
    })
  })
})
```

### 4.2 测试数据工厂

```js
// tests/factories/user.js
import { faker } from '@faker-js/faker'

export function createUser(overrides = {}) {
  return {
    id: faker.number.int(),
    name: faker.person.fullName(),
    email: faker.internet.email(),
    createdAt: faker.date.recent(),
    ...overrides
  }
}

export function createUserList(count = 5, overrides = {}) {
  return Array.from({ length: count }, () => createUser(overrides))
}

// 使用
const user = createUser({ name: 'Test User' })
```

### 4.3 共享 Fixture

```js
// tests/fixtures/composables.js
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

export function mountWithPinia(Component, options = {}) {
  return mount(Component, {
    global: {
      plugins: [createPinia()],
      ...options.global
    },
    ...options
  })
}
```

---

## 5. 容易定位问题的实践

### 5.1 Source Map 配置

**生产环境**（vite.config.js）：
```js
export default defineConfig({
  build: {
    sourcemap: 'hidden',  // hidden-source-map，生成但不在 JS 末尾引用
    // sourcemap: true     // 普通 source map，会暴露源码（不安全）
  }
})
```

**测试环境**（vitest.config.js）：
```js
export default defineConfig({
  test: {
    environment: 'happy-dom',
    sourcemap: true,  // 测试错误指向原始源码
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{js,vue}'],
      exclude: ['src/**/*.spec.{js,ts}', 'src/**/*.test.{js,ts}']
    }
  }
})
```

### 5.2 错误堆栈格式化

```js
// src/test/setup.js
import { beforeAll, afterEach, afterAll } from 'vitest'
import { cleanup } from '@testing-library/vue'

// 全局错误处理
beforeAll(() => {
  process.on('uncaughtException', (err) => {
    console.error('Uncaught exception in test:', err)
  })
})

// 测试后清理 DOM
afterEach(() => {
  cleanup()
})

// 失败时打印组件快照
afterEach((ctx) => {
  if (ctx.task.result?.state === 'fail') {
    console.log('Component HTML:')
    // 打印当前 wrapper 的 HTML
  }
})
```

### 5.3 @vitest/ui 可视化调试

```bash
# 启动调试 UI
npm run test:ui

# 或：
npx vitest --ui
```

**功能**：
- 实时看到每个测试的状态
- 点击失败的测试，查看错误堆栈
- 重新跑单个测试
- 覆盖率可视化

**VSCode 集成**：
```json
// .vscode/settings.json
{
  "vitest.enable": true,
  "vitest.commandLine": "npm run test"
}
```

### 5.4 Vue DevTools 启用

**开发环境**（默认启用）：无配置

**生产环境调试**（临时）：
```js
// src/main.js（仅调试时使用）
if (import.meta.env.MODE === 'production' && window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
  window.__VUE_DEVTOOLS_GLOBAL_HOOK__.enable = true
}
```

---

## 6. 性能优化实践

### 6.1 升级 happy-dom（vs jsdom）

```js
// vitest.config.js
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',  // 改用 happy-dom
    // 性能优化配置
    isolate: false,            // 关闭测试隔离（适合单元测试）
    pool: 'threads',           // 使用线程池
    poolOptions: {
      threads: {
        singleThread: false,   // 允许多线程
        isolate: false,        // 进一步加速
      }
    },
    include: ['src/**/*.{test,spec}.{js,ts}'],
    exclude: ['node_modules', 'dist', 'e2e'],
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
```

**性能提升**：
- 启动时间：1.5s → 0.5s（3x 快）
- 内存占用：200MB → 50MB（4x 少）
- 单元测试速度：2-3x 提升

### 6.2 智能缓存

```js
export default defineConfig({
  test: {
    cache: {
      dir: './node_modules/.cache/vitest',  // 缓存目录
    },
    // 智能 watch
    watch: {
      ignore: ['**/node_modules/**', '**/dist/**']
    }
  }
})
```

### 6.3 智能并行

```js
export default defineConfig({
  test: {
    pool: 'threads',
    poolOptions: {
      threads: {
        maxThreads: 4,        // 最多 4 线程
        minThreads: 1,
        singleThread: false
      }
    }
  }
})
```

### 6.4 测试分层运行

```json
// package.json
{
  "scripts": {
    "test:unit": "vitest run --reporter=verbose src/**/*.{test,spec}.{js,ts} -t 'unit'",
    "test:component": "vitest run --reporter=verbose src/**/*.{test,spec}.{js,ts} -t 'component'",
    "test:e2e": "playwright test",
    "test:quick": "vitest run --bail 1 --reporter=verbose",
    "test:ci": "vitest run --coverage --reporter=verbose --bail=5"
  }
}
```

---

## 7. 完整的最佳实践配置

### 7.1 package.json

```json
{
  "devDependencies": {
    "vitest": "^2.1.0",
    "@vitest/ui": "^2.1.0",
    "@vitest/coverage-v8": "^2.1.0",
    "@vue/test-utils": "^2.4.6",
    "happy-dom": "^15.0.0",
    "msw": "^2.6.0",
    "@playwright/test": "1.60.0",
    "@faker-js/faker": "^9.0.0",
    "@testing-library/vue": "^8.1.0"
  }
}
```

### 7.2 推荐的测试文件结构

```
src/
├── components/
│   ├── UserCard/
│   │   ├── UserCard.vue
│   │   ├── UserCard.spec.js           # 组件测试
│   │   └── __snapshots__/             # 快照
│   └── ...
├── composables/
│   ├── useUser.js
│   └── useUser.spec.js                # 组合式函数测试
└── test/
    ├── setup.js                       # 全局 setup
    ├── factories/                     # 测试数据工厂
    │   ├── user.js
    │   └── product.js
    └── fixtures/                      # 共享 fixture
        └── mount.js

e2e/
├── features/
│   ├── login.spec.js                  # Playwright E2E
│   └── ...
└── fixtures/                          # E2E 共享数据

tests/                                 # Python 测试
├── unit/
├── integration/
└── e2e/
```

---

## 8. 检查清单

### 写测试前

- [ ] 是否能用单元测试解决？优先单元测试
- [ ] 是否需要测试组件交互？用组件测试
- [ ] 是否需要跨页面？用 E2E

### 写测试时

- [ ] Source Map 已开启？
- [ ] happy-dom 已配置？
- [ ] 用了 MSW mock API？
- [ ] 测试工厂创建数据？
- [ ] 单个测试 < 1 秒？

### 写测试后

- [ ] 失败时能定位到源码？
- [ ] 测试运行 < 5 分钟？
- [ ] 用了并行执行？
- [ ] 有覆盖率报告？

---

## 9. 工具链总结

```
开发环境:
  - VSCode + Vitest 插件 (即时反馈)
  - @vitest/ui (可视化调试)
  - Vue DevTools (组件树/Pinia)

测试运行时:
  - happy-dom (快 2-3x)
  - MSW (API mocking)
  - Source Map (错误定位)

CI/CD:
  - vitest run (非 watch 模式)
  - 并行执行 (--threads=4)
  - 覆盖率报告 (v8)
  - HTML 报告 (--reporter=html)
```

---

## 10. 性能基准

| 指标 | 当前（jsdom） | 优化后（happy-dom + 并行） |
|------|--------------|------------------------|
| 启动时间 | 1.5s | 0.5s |
| 100 个单元测试 | 30s | 8s |
| 内存占用 | 200MB | 50MB |
| Source Map 错误定位 | 不可用 | 可用 |
| API Mock 性能 | 慢（模块 mock） | 快（MSW） |

Sources:
- [Vue.js 官方测试指南](https://cn.vuejs.org/guide/scaling-up/testing)
- [State of Frontend Testing 2026](https://scanlyapp.com/blog/state-of-frontend-testing-2026)
- [Vitest Component Testing](https://vitest.dev/guide/browser/component-testing)
- [Vue 线上代码调试全攻略](https://juejin.cn/post/7633752260267540495)
- [Debugging Minified JavaScript](https://www.codeformatter.in/blog-debugging.html)
