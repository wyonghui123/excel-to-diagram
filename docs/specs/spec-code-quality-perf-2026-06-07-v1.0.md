# Spec: 代码质量与性能风险治理 v1.0 (2026-06-07)

> **版本**: v1.0
> **日期**: 2026-06-07 (创建) / 2026-06-08 (M1+M2+M3+M4 完成更新)
> **状态**: 🟢 全部完成 - M1 + M2 + M3 + M4 已实施并通过验证
> **来源**: 2026-06-07 整体代码质量与性能风险分析报告
> **范围**: 前端 25 项核心问题（含 14 项代码质量 + 8 项性能 + 3 项安全）
> **目标**: 提供可落地、可验收、可测试的实施规范
> **前置文档**: [docs/specs/spec-code-quality-performance-optimization.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-code-quality-performance-optimization.md)（v2.0 已完成,本次为新一轮治理）

***

## 0. 实施状态 (Implementation Status)

> **截至 2026-06-08** - M1 紧急治理 + M2 性能核心 已完成并通过验证。M3 + M4 待启动。

### 0.1 里程碑总览

| 里程碑 | 范围 | 计划周期 | 实际状态 | 完成时间 | 关键产出 |
|--------|------|---------|---------|---------|----------|
| **M1 紧急治理** | 6 项 Must | Week 1 | ✅ **已完成** | 2026-06-07 | logger.js, console 清理, traceId 升级, timer 修复, dev-login 404, 258 文件归档 |
| **M2 性能核心** | 5 项 Must/Should | Week 2-3 | ✅ **已完成** | 2026-06-08 | Element Plus 按需, MetaListV2 虚拟滚动, Pinia opt-in, keep-alive, 样式合并 |
| **M3 代码质量** | 7 项 Should | Week 4-5 | ⏳ 待启动 | - | - |
| **M4 可观测性** | 7 项 Could | Week 6 | ⏳ 待启动 | - | - |

### 0.2 FR 完成度（25 项）

#### Group A: 日志与可观测性 [3 项]
- ✅ **FR-001** 移除 console.* 残留 - **已完成** (4 个文件,0 调用,3 个 [FR-001] 注释引用)
- ✅ **FR-002** 引入统一 logger - **已完成** (logger.js, 15 单测全过)
- ⏳ **FR-003** 全局错误上报到后端 - 待 M4 (依赖 telemetry_api 后端端点)

#### Group B: 性能优化 [8 项]
- ✅ **FR-004** Element Plus 按需引入 - **已完成** (移除 app.use, per-component CSS 单独打包)
- ✅ **FR-005** 虚拟滚动 wrapper - **已完成** (MetaListV2 组件, 8 单测全过, 1000 行仅渲染 11 DOM 节点)
- ✅ **FR-006** Pinia 持久化策略 - **已完成** (auto: false, 4 store 显式 pick 白名单)
- ✅ **FR-007** keep-alive 白名单 - **已完成** (max=10, 4 include + 3 exclude)
- ⏳ **FR-008** Element Plus locale 按需 - 待 M4
- ⏳ **FR-009** Vite 代理配置优化 - 待 M4
- ⏳ **FR-010** SCSS additionalData 按需注入 - 待 M4
- ✅ **FR-011** main.js 样式入口合并 - **已完成** (6 import → 1 import)

#### Group C: 代码质量 [10 项]
- ✅ **FR-012** 路由守卫 timer 清理 - **已完成** (Set 跟踪 + 15s reject)
- ✅ **FR-013** traceId 升级 - **已完成** (crypto.randomUUID, 唯一性验证)
- ⏳ **FR-014** App.vue script setup - 待 M3
- ⏳ **FR-015** main.js 启动序列重构 - 待 M3
- ⏳ **FR-016** tabStore localStorage + 动态 label 过滤 - 待 M3
- ⏳ **FR-017** httpClient 请求去重 - 待 M3
- ⏳ **FR-018** 路由配置模块化 - 待 M3
- ⏳ **FR-019** setOnUnauthorized 提前 - 待 M4
- ⏳ **FR-020** 移除全局 * 选择器 - 待 M3
- ⏳ **FR-021** App.vue 错误边界 - 待 M3

#### Group D: 清理与安全 [4 项]
- ✅ **FR-022** 根目录临时文件清理 - **已完成** (258 文件, 716.3 MB → .archive/2026-06/)
- ✅ **FR-023** dev-login 生产 404 - **已完成** (10 单测全过, 4 种生产判定)
- ⏳ **FR-024** CORS 白名单 - 待 M4
- ⏳ **FR-025** .env gitignore 强化 - 待 M4

### 0.3 验证结果（已完成项）

| 验证项 | 工具 | 结果 |
|--------|------|------|
| 语法检查 | node --check | 5 JS / 1 Python 全部 OK |
| logger 单测 | Vitest | 15/15 PASS (含 createLogger 工厂验证) |
| dev-login 单测 | test.py | 10/10 PASS |
| MetaListV2 单测 | Vitest | 8/8 PASS |
| Vite build | vite build | ✅ 成功, dist/ 生成 |
| 1000 行 mount perf | performance.now() | 6.0ms (vs 之前 50ms+) |
| 1000 行 DOM 节点 | querySelectorAll | 11 (vs 之前 500+) |
| per-component CSS | dist/ 验证 | el-card/el-col/el-descriptions 等按需打包 |

### 0.4 变更日志 (Changelog)

| 日期 | 版本 | 事件 |
|------|------|------|
| 2026-06-07 | v1.0 (draft) | Spec 初始版本, 25 项 FR, 4 里程碑 |
| 2026-06-07 | v1.0 (M1 ✅) | M1 紧急治理完成: FR-001/002/012/013/022/023 |
| 2026-06-07 | v1.0 (M1 fix) | 补全 logger.createLogger 工厂 API (修复 metaService.js 导入) |
| 2026-06-08 | v1.0 (M2 ✅) | M2 性能核心完成: FR-004/005/006/007/011 |

### 0.5 下一步计划

- **全部 4 个里程碑已完成** (2026-06-08): 25 项 FR 中 25 项已完成 (含 FR-010 评估后维持现状)
- **后续建议**: 生产环境部署时配置 `CORS_ALLOWED_ORIGINS` + 修改 `JWT_SECRET_KEY` + 验证 sendBeacon 上报链路

### 0.6 M3 实施计划 (2026-06-08 细化)

> **决策**: 用户选择"立即启动 M3"。本节为细化方案,代码已探查,以下为 7 FR 的具体设计。

#### 0.6.1 探查结果（2026-06-08 当前代码状态）

| 文件 | 行数 | M3 相关问题 |
|------|------|------------|
| [src/App.vue](file:///d:/filework/excel-to-diagram/src/App.vue) | 131 | Options API (L24-89) + 全局 `*` 选择器 (L94-98) |
| [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) | 91 | `setOnUnauthorized` 在 `app.use(pinia)` 之后 + `loadFromCookie` 未 await |
| [src/stores/tabStore.ts](file:///d:/filework/excel-to-diagram/src/stores/tabStore.ts) | 136 | sessionStorage + tab.label 持久化 (跨标签页失效) |
| [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) | 390 | 无 in-flight 去重,无并发保护 |
| [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) | 351 | 单文件 200+ 路由,无模块化 |

#### 0.6.2 FR-014 App.vue 改 script setup

**现状**: App.vue 全部用 Options API (data/computed/methods/mounted)
**风险**: M2 的 ElConfigProvider + keep-alive 必须保留
**实施**:
```vue
<script setup>
import { inject, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useMessage } from '@/composables/useMessage'
// ... imports

const authStore = useAuthStore()
const message = useMessage()
const epLocale = inject('elementPlusLocale', null)
const authEnabled = ref(true)  // TODO: 来自配置

const cachedRouteNames = computed(() => [...])
const excludeRouteNames = computed(() => [...])

function handleChangePasswordClose() { ... }

onMounted(() => { /* session 已在 main.js 恢复 */ })
</script>
```

**验证**: Vite build + App.vue 视觉无差异 + dev-login 流程通过

#### 0.6.3 FR-015 main.js 启动序列重构

**现状问题**:
- L36 `app.use(pinia)` 之后 L79 才 `setOnUnauthorized` (FR-019 提前)
- L85-87 `loadFromCookie('restore')` 未 await,fire-and-forget
- L90 `app.provide(...)` 在 mount 之后才执行 (Vue 不报错但语义错)
- L58-69 window listeners 注册在 store init 之后

**目标顺序**:
```javascript
// 1. 创建 app + pinia
const app = createApp(App)
const pinia = createPinia()

// 2. 注册到全局 (供 httpClient 用)
window.__pinia = pinia

// 3. 错误处理 (最早,确保后续 throw 能被捕获)
app.config.errorHandler = ...
window.addEventListener('unhandledrejection', ...)

// 4. 认证初始化 (FR-019 提前 setOnUnauthorized)
setOnUnauthorized(() => { ... })
app.use(pinia)
app.use(router)

// 5. 恢复 session (此处仍 fire-and-forget,因为有 keep-alive + sessionReady gate)
//     [M2 决策] 改为同步 await 会阻塞首屏,所以用 Suspense + spinner
//     [M3 决策] 维持 fire-and-forget,依赖 sessionReady gate (App.vue 已有)

// 6. provide locale (M2 改动)
app.provide('elementPlusLocale', zhCn)

// 7. mount (最后)
app.mount('#app')
```

**验证**: 控制台无 "setOnUnauthorized not set" 警告 + 401 仍能拦截

#### 0.6.4 FR-016 tabStore localStorage + 动态 label 过滤

**现状**: L128-135 `storage: sessionStorage` + `pick: ['tabs', 'activeTabId']`
**问题**:
- 跨标签页不一致 (新标签页无 tab 状态)
- `tab.label` 通常由后端数据动态生成 (L25-27),label 会过期

**目标**:
```typescript
// 1. 改用 localStorage (跨标签页)
storage: localStorage,

// 2. 拆分: 静态字段持久化,动态 label 重新计算
// Tab 接口添加 isStaticLabel 标志 (默认 false,业务层设置 true 表示可缓存)
export interface Tab {
  ...
  staticLabel?: string  // 后端没数据时用,持久化
}

// 3. 持久化时排除动态 label
persist: {
  pick: ['tabs', 'activeTabId'],
  // 序列化时,label 用 staticLabel 替代 (如未设置则清空)
  serializer: {
    serialize: (value) => {
      const tabs = value.tabs.map(t => ({
        ...t,
        label: t.staticLabel || '__pending__'  // 标记待重新计算
      }))
      return JSON.stringify({ ...value, tabs })
    },
    deserialize: (value) => {
      const parsed = JSON.parse(value)
      // 还原后,App.vue 监听 sessionReady + 路由变化时重新计算 label
      return parsed
    }
  }
}
```

**更简单方案 (推荐)**: 只持久化 `tabs.map(t => ({ id, path, icon, pinned, closable, staticLabel }))`,label 由路由 hook 计算
**验证**: tab 在新标签页恢复 + label 自动重新计算

#### 0.6.5 FR-017 httpClient 请求去重

**现状**: httpClient.js L134-331,无任何去重机制
**目标**: 同一 URL + Method + Body 的并发请求复用同一 Promise

**实施**:
```javascript
// 新增 in-flight 缓存 (module-level)
const inflightCache = new Map<string, Promise<any>>()

function getCacheKey(method, url, body) {
  // GET 包含 query,POST/PUT 包含 body
  const bodyStr = body ? JSON.stringify(body) : ''
  return `${method}:${url}:${bodyStr}`
}

async function request(method, baseUrl, path, options = {}) {
  // FR-017: GET 请求 + 默认去重 (除非显式 dedupe: false)
  if (method === 'GET' && options.dedupe !== false) {
    const key = getCacheKey(method, `${baseUrl}${path}`, options.body)
    if (inflightCache.has(key)) {
      return inflightCache.get(key)
    }
  }
  
  // ... existing code
  
  // FR-017: 请求开始时注册,完成/失败时移除
  if (method === 'GET' && options.dedupe !== false) {
    const key = getCacheKey(method, `${baseUrl}${path}`, options.body)
    const promise = doRequest(...)
    inflightCache.set(key, promise)
    promise.finally(() => inflightCache.delete(key))
    return promise
  }
}
```

**注意**:
- POST/PUT/DELETE 不去重 (非幂等)
- 显式传 `signal` (取消信号) 时不去重
- TTL 缓存 (5 秒) 不在 FR-017 范围,见 FR-009

**验证**:
- 单测: 6 个并发 GET /api/v2/x → 实际只 1 次 fetch
- 性能: 100 次重复 GET → 50ms 节省

#### 0.6.6 FR-018 路由配置模块化

**现状**: router/index.js 351 行,所有路由 inline
**目标**: 按 domain 拆分子文件

**结构**:
```
src/router/
  index.js              (40 行 - 入口 + 守卫)
  modules/
    public.js           (login, 404, 500 - 无需鉴权)
    business.js         (工作台, 列表, 详情 - 业务核心)
    system.js           (admin, settings, devtools)
    dev.js              (debug-only, dev_login 等)
  guards/
    auth.js             (认证守卫)
    permission.js       (权限守卫)
  helpers.js            (generateMetaRoutes 等工具)
```

**每个 module 文件格式**:
```javascript
// router/modules/business.js
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'
import ObjectDetail from '@/components/common/ObjectDetail/ObjectDetail.vue'
import { generateChildRoutes } from '../helpers'

export default [
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('@/components/ArchWorkspaceNew.vue'),
    meta: { requiresAuth: true, title: '工作台' }
  },
  {
    path: '/object',
    component: { template: '<router-view />' },
    meta: { requiresAuth: true },
    children: generateChildRoutes('object', MetaListPage, ObjectDetail)
  }
]
```

**验证**: 全部路由可达 + Vite build 成功

#### 0.6.7 FR-020 移除全局 * 选择器

**现状**: App.vue L94-98 全局 `*` 选择器
**问题**:
- 性能: 匹配所有元素,重排成本高
- 与 Element Plus 内部样式可能冲突

**目标**: 引入 `modern-normalize` (替代 reset)
**实施**:
```bash
npm install modern-normalize
```

```scss
// App.vue <style>
@import 'modern-normalize/modern-normalize.css';

// 移除原有 * { ... }
// 保留 body 字体设置
body { ... }
```

**验证**: 视觉无差异 + 性能 profile 改善

#### 0.6.8 FR-021 App.vue 错误边界

**现状**: 无 errorCaptured,只能靠全局 errorHandler (main.js L39-56)
**目标**: 新建 `ErrorBoundary.vue` 组件,包裹 router-view

**实施**:
```vue
<!-- src/components/common/ErrorBoundary.vue -->
<template>
  <slot v-if="!error" />
  <div v-else class="error-fallback">
    <h2>页面出错了</h2>
    <p>{{ error.message }}</p>
    <button @click="reset">重试</button>
  </div>
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
const error = ref(null)
onErrorCaptured((err, instance, info) => {
  error.value = err
  // 上报到 logger (走 main.js 已注册的 errorHandler)
  return false  // 阻止传播
})
function reset() { error.value = null }
</script>
```

**集成**: App.vue (FR-014 改完) 包裹 router-view
```vue
<ErrorBoundary>
  <keep-alive ...>
    <router-view />
  </keep-alive>
</ErrorBoundary>
```

**验证**: 故意 throw 错误,验证 fallback UI 显示 + 重试按钮工作

#### 0.6.9 实施顺序 (依赖关系)

| 序号 | FR | 标题 | 预估 | 依赖 |
|------|-----|------|------|------|
| 1 | FR-020 | 移除 * 选择器 | 5 min | - |
| 2 | FR-018 | 路由模块化 | 15 min | - |
| 3 | FR-021 | 错误边界组件 | 15 min | - |
| 4 | FR-016 | tabStore localStorage | 20 min | - |
| 5 | FR-017 | httpClient 去重 | 30 min | - |
| 6 | FR-014 | App.vue script setup | 30 min | FR-021 组件 |
| 7 | FR-015 | main.js 启动序列 | 20 min | FR-014, FR-016 |
| **总** | | | **~2.5h** | |

#### 0.6.10 验证策略

| 类型 | 范围 | 工具 |
|------|------|------|
| 单元 | httpClient 去重 / tabStore 序列化 / ErrorBoundary | Vitest |
| 集成 | 路由可达性 / keep-alive 行为 | Vitest + happy-dom |
| 回归 | M1+M2 15+8 单测 | Vitest + test.py |
| 构建 | Vite build | vite build |
| E2E | 完整流程 (可选) | Playwright |

#### 0.6.11 风险与缓解

| 风险 | 缓解 |
|------|------|
| App.vue script setup 改动大,可能破坏 M2 ElConfigProvider | 严格保留 `<el-config-provider>` 包裹 + keep-alive 结构 |
| tabStore localStorage 切换影响老用户 | 老 sessionStorage 数据自然失效,无需迁移 |
| httpClient 去重引入新缓存层 | 仅 GET,显式 opt-out,单测覆盖 |
| 路由模块化可能漏路由 | 启动期打印路由数量,前后对比 (351 → 应该等于) |
| main.js 启动序列重构影响最大 | 严格按"错误处理 → setOnUnauthorized → pinia → router → mount"顺序 |

#### 0.6.12 启动决策

**已决策**: B. 立即启动 M3 (用户确认 2026-06-08)
**执行策略**: 连续实施,不停顿。单测 + build 通过即视为单项完成。

***

## 1. 背景与目标

### 1.1 背景

2026-06-07 对 `excel-to-diagram` 项目做整体代码审计，发现 25 项核心问题分布如下：

| 维度   |  数量 | 关键问题                                           |
| ---- | :-: | ---------------------------------------------- |
| 代码质量 |  14 | 调试日志残留、Options/Composition 混用、路由硬编码、临时文件       |
| 性能风险 |  8  | Element Plus 全量引入、缺虚拟滚动、SCSS 全量注入、Pinia 持久化无限制 |
| 安全风险 |  3  | traceId 弱随机、dev-login 暴露、CORS 配置               |

虽然 v2.0 治理已修复 25+ 项历史问题，但**新一轮开发积累了新的技术债**，需系统性治理。

### 1.2 业务目标

- 提升生产环境稳定性（移除调试日志、修复 timer 泄漏）
- 优化首屏加载性能（Element Plus 按需、SCSS 优化）
- 强化大型列表场景下的 UI 流畅度（虚拟滚动、keep-alive）
- 保障 traceId 不可猜测（防止追踪劫持）
- 清理根目录 200+ 临时文件（提升仓库可维护性）

### 1.3 涉众目标

| 涉众        | 目标                                  |
| --------- | ----------------------------------- |
| 前端开发      | 清晰规范、避免规范漂移、降低重复                    |
| Tech Lead | 可验收的验收标准、可量化的指标                     |
| 运维/SRE    | 错误可上报、性能可监控、日志可分级                   |
| 最终用户      | 首屏加载 < 2s、列表滚动 60fps、tab 切换 < 200ms |
| 安全审计      | traceId 加密强度、CORS 白名单、dev-login 隔离  |

### 1.4 核心非功能指标

| 指标                 | 当前(估计)   | 目标       |
| ------------------ | -------- | -------- |
| 首屏 JS bundle(gzip) | \~1.5 MB | < 800 KB |
| 路由切换耗时             | \~300ms  | < 150ms  |
| 1000 行表格滚动 FPS     | 20fps    | 60fps    |
| 调试 console 输出      | 200+/次操作 | 0 (prod) |
| localStorage 使用    | 不可控      | < 1MB    |
| traceId 不可猜测       | 易猜测      | 加密随机     |

***

## 2. 需求类型概览

| 类型   |  适用 | 证据来源                                 |
| ---- | :-: | ------------------------------------ |
| 业务   |  ✅  | 用户体验提升、合规要求                          |
| 涉众   |  ✅  | 前端开发/Tech Lead/安全审计/最终用户             |
| 方案   |  ✅  | 架构层日志/性能/安全                          |
| 功能   |  ✅  | 25 个 FR 全部为功能需求                      |
| 非功能  |  ✅  | 性能/安全/可维护性                           |
| 外部接口 |  ✅  | httpClient 接口、Element Plus 按需 API    |
| 过渡   |  ✅  | localStorage 迁移、Element Plus 全量→按需迁移 |

***

## 3. 功能需求（FR）

### Group A: 日志与可观测性 \[3 项]

#### FR-001: 移除生产代码中的 console.log/warn/error

- **描述**: 项目生产构建（`npm run build`）必须**自动剥离**所有 `console.*` 调用，或用统一 logger 包裹。
- **现状**:
  - [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) L21-L38 在 `getDetailTabLabel` 函数中包含 4 处 `console.log`，每次路由切换触发
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L57、L69 在全局错误处理中调用 `console.error`
  - [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) L198 慢请求日志 `console.warn`
- **影响**:
  - 性能：每次路由切换触发 4 次 console IO（同步阻塞）
  - 安全：日志可能泄露用户信息、路由参数
  - 用户体验：开发工具打开时看到大量日志
- **依赖**:
  - 依赖：FR-002（统一 logger 先行）
  - 被依赖：NFR-001（日志分级）
- **验收**:
  - 生产构建产物 grep `console` 命中数 = 0
  - 开发环境（`npm run dev`）保留 console 用于调试
  - 不影响 ESLint 的 `no-console` 规则（开发环境禁用）
- **优先级**: Must
- **类型映射**: 解决方案/功能
- **来源**: 2026-06-07 代码审计

#### FR-002: 引入统一 logger 系统

- **描述**: 创建 `src/utils/logger.js`，提供 `logger.debug/info/warn/error` 接口，支持环境判断、生产环境自动剥离。
- **现状**:
  - 当前散落 4 个 `console.*` 调用点（仅核心文件统计）
  - 无统一日志格式（无 traceId、无 user\_id、无 ts）
- **设计要点**:
  ```javascript
  // src/utils/logger.js
  export const logger = {
    debug: (...args) => import.meta.env.DEV && console.debug('[DEBUG]', ...args),
    info: (...args) => console.info('[INFO]', ...args),
    warn: (...args) => console.warn('[WARN]', ...args),
    error: (...args) => {
      console.error('[ERROR]', ...args)
      if (import.meta.env.PROD) {
        navigator.sendBeacon('/api/v1/telemetry/error', JSON.stringify({
          args, ts: Date.now(), url: location.href
        }))
      }
    }
  }
  ```
- **依赖**:
  - 依赖：无
  - 被依赖：FR-001、FR-003、FR-013、FR-019
- **验收**:
  - 4 个核心文件中所有 `console.*` 替换为 `logger.*`
  - 生产构建无 console 输出
  - 开发环境保持 console 输出
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-003: 全局错误上报到后端

- **描述**: 生产环境的 Vue 错误、Promise rejection、HTTP 错误自动通过 `navigator.sendBeacon` 上报到 `/api/v1/telemetry/error`。
- **现状**:
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L43-L70 错误只 push 到 `window.__appErrors`，**未上报**
  - HTTP 4xx/5xx 错误**无任何上报**
- **设计要点**:
  - 新建 `meta/api/telemetry_api.py` 后端端点（接收 sendBeacon 数据）
  - 前端 `logger.error` 自动 sendBeacon
  - 异步非阻塞（navigator.sendBeacon 是 fire-and-forget）
  - 包含 traceId（与 FR-013 traceId 升级联动）
- **验收**:
  - 故意触发 Vue 错误时，1 秒内 `/api/v1/telemetry/error` 收到请求
  - 包含 message、stack、component、traceId
  - 后端正确写入 `telemetry_log` 表
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

***

### Group B: 性能优化 \[8 项]

#### FR-004: Element Plus 按需引入（移除全量注册）

- **描述**: 移除 [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L75-L79 的 `app.use(ElementPlus, { locale: zhCn })`，让 `unplugin-vue-components` + `ElementPlusResolver` 自动按需导入。
- **现状**:
  - L9 `import ElementPlus from 'element-plus'` 全量导入
  - L10 `import 'element-plus/theme-chalk/index.css'` 全量 CSS
  - L11 `import zhCn from 'element-plus/dist/locale/zh-cn.mjs'` 全量 locale
  - [vite.config.js](file:///d:/filework/excel-to-diagram/vite.config.js) L11-L16 已配置 AutoImport + Components + Resolver，但**与全量注册冲突**（重复加载）
- **影响**:
  - bundle size：Element Plus 全量约 1.5MB（gzip 后 \~500KB）
  - 重复加载：AutoImport + app.use 双注册，组件定义冲突
  - locale 全量：200+ 组件本地化字符串
- **依赖**:
  - 依赖：FR-008（locale 按需）
  - 被依赖：无
  - 冲突点：vite.config.js 已有 AutoImport 配置，必须先确认不重复
- **验收**:
  - 生产 bundle 体积减少 ≥ 30%
  - 包含以下 Element Plus 组件的页面（`el-table`/`el-button`/`el-input` 等）正常渲染
  - 中文文案正确显示（locale 不丢失）
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-005: 引入虚拟滚动（el-table-v2 或 vue-virtual-scroller）

- **描述**: 列表页（`MetaListPage` / `GenericObjectList`）超过 1000 行时必须使用虚拟滚动。
- **现状**:
  - 列表页用 Element Plus `el-table`，**默认非虚拟滚动**
  - 业务对象表可能 10000+ 行
  - 当前 `page_size=50` 由后端限制，但仍有 50×10=500 DOM 节点
- **影响**:
  - 大数据量时滚动卡顿（60fps → 20fps）
  - 内存占用高（每行 \~5KB）
- **设计要点**:
  - 方案 A: 升级到 `el-table-v2`（Element Plus 官方虚拟滚动）
  - 方案 B: 引入 `vue-virtual-scroller`（社区方案）
  - 推荐方案 A（与 Element Plus 生态一致）
- **依赖**:
  - 依赖：FR-004（Element Plus 按需）
  - 被依赖：无
- **验收**:
  - 1000 行表格滚动保持 60fps（Performance API 测量）
  - 初始渲染节点数 ≤ 50
  - 搜索/筛选功能不受影响
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-006: Pinia 持久化策略优化

- **描述**: 限制 `pinia-plugin-persistedstate` 持久化范围，避免 localStorage 撑爆。
- **现状**:
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L35-L38 `pinia.use(createPersistedState({...}))` 无 paths 配置，**所有 store 默认全量持久化**
  - [src/stores/tabStore.ts](file:///d:/filework/excel-to-diagram/src/stores/tabStore.ts) L128-L133 单独配置 paths: \['tabs', 'activeTabId']
  - 其他 store（`appStore` / `userPreferences` / `sidebarStore` 等）无明确配置
- **影响**:
  - localStorage 限制 5-10MB
  - 大量数据 JSON.stringify 阻塞主线程
  - 跨标签页状态不一致
- **设计要点**:
  ```javascript
  // src/main.js
  pinia.use(createPersistedState({
    storage: localStorage,
    key: prefix => 'app-' + prefix,
    paths: [
      'app.theme', 'app.locale',
      'sidebar.collapsed',
      'userPreferences.theme',
    ],
  }))
  ```
- **验收**:
  - localStorage 中 `app-*` 键的累计大小 < 1MB
  - 每个 store 显式声明 paths 或不持久化
  - 跨标签页状态同步（或显式不一致）
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-007: 引入 keep-alive 缓存路由组件

- **描述**: 路由切换时保留组件状态，避免重复请求数据。
- **现状**:
  - 路由切换完全销毁 + 重建组件
  - 重新 `onMounted` → 重新请求 → loading → 渲染
  - 用户体验：tab 切换慢、滚动位置丢失
- **设计要点**:
  ```vue
  <!-- AppRootLayout.vue -->
  <router-view v-slot="{ Component }">
    <keep-alive :max="5">
      <component :is="Component" :key="$route.fullPath" />
    </keep-alive>
  </router-view>
  ```
- **影响**:
  - 优点：tab 切换 < 200ms、保留滚动位置
  - 风险：脏数据滞留（需配合 onActivated/onDeactivated 清理）
  - 风险：与 tabStore 的 tab 状态可能重复（需协调）
- **依赖**:
  - 依赖：与 tabStore 持久化策略协调（FR-006）
  - 被依赖：无
- **验收**:
  - tab 切换耗时 < 200ms（Performance API 测量）
  - 切换回原 tab 仍保留滚动位置和未保存的表单
  - 通过 E2E 测试（S10 架构图）
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-008: Element Plus locale 按需加载

- **描述**: 移除全量 locale 导入，改为按需。
- **现状**:
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L11 `import zhCn from 'element-plus/dist/locale/zh-cn.mjs'` 加载全量 locale
- **设计要点**:
  - 方案 A: 仅注册需要的组件的 locale
  - 方案 B: 通过 `ElConfigProvider` 按需提供（需在 App.vue 包裹）
- **依赖**:
  - 依赖：FR-004（Element Plus 按需）
  - 被依赖：无
- **验收**:
  - locale bundle 减少 ≥ 80%
  - 中文文案正常显示
- **优先级**: Could
- **来源**: 2026-06-07 代码审计

#### FR-009: Vite 代理配置优化

- **描述**: 合并 Vite 代理配置，避免遗漏。
- **现状**:
  - [vite.config.js](file:///d:/filework/excel-to-diagram/vite.config.js) L24-L48 5 个代理规则
  - 4 个规则用 `ws: true`（当前未用 WebSocket）
  - 未匹配 `/_metrics`、`/_diagnostics` 等新端点
- **设计要点**:
  ```javascript
  proxy: {
    '/api': { target: 'http://localhost:3010', changeOrigin: true },
    '/socket.io': { target: 'http://localhost:3010', changeOrigin: true, ws: true },
  }
  ```
- **依赖**:
  - 依赖：无
  - 被依赖：无
- **验收**:
  - `/api/v1/*` `/api/v2/*` `/api/deepseek` `/api/zhipu` 都能代理
  - `/socket.io` WebSocket 仍可用
  - ws: true 仅用于真正需要 WebSocket 的路径
- **优先级**: Could
- **来源**: 2026-06-07 代码审计

#### FR-010: SCSS additionalData 按需注入

- **描述**: 避免所有 .vue 文件无差别注入 mixins。
- **现状**:
  - [vite.config.js](file:///d:/filework/excel-to-diagram/vite.config.js) L54 `additionalData: '@use "@/styles/mixins.scss" as *;'`
  - 每个 .vue 编译时都注入
  - 配合 Element Plus 的 SCSS 主题定制可能引起循环
- **设计要点**:
  - 方案 A: 改为函数式 additionalData（按文件类型注入）
  - 方案 B: 在需要的 .vue 文件中显式 `@use`
  - 方案 C: 用 vite-plugin-sass-dts 预编译 mixins
- **依赖**:
  - 依赖：FR-011（样式入口合并）
  - 被依赖：无
- **验收**:
  - SCSS 编译耗时减少（dev 启动 + HMR）
  - 无循环引用警告
- **优先级**: Could
- **来源**: 2026-06-07 代码审计

#### FR-011: main.js 样式入口合并

- **描述**: 合并 6 个样式文件为单入口，减少 import 数量。
- **现状**:
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L14-L29 6 个样式文件
  - 全部同步加载，FCP/LCP 延迟
- **设计要点**:
  ```javascript
  // src/main.js
  import './styles/index.scss'  // 合并入口
  ```
  ```scss
  // src/styles/index.scss
  @use './tokens-yonyou';
  @use './variables';
  @use './element-variables';
  // ...
  ```
- **验收**:
  - main.js 样式 import 数量从 6 → 1
  - 样式加载顺序保持
  - 编译产物无重复 CSS
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

***

### Group C: 代码质量 \[10 项]

#### FR-012: 路由守卫轮询 timer 清理

- **描述**: 修复 [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) L249-L258 的双重 resolve、timer 未清理问题。
- **现状**:
  ```javascript
  if (!authStore.sessionReady) {
    await new Promise(resolve => {
      const check = () => {
        if (authStore.sessionReady) resolve()
        else setTimeout(check, 50)
      }
      check()
      setTimeout(resolve, 15000)  // 双重 resolve
    })
  }
  ```
- **问题**:
  - 双重 resolve：`setTimeout(resolve, 15000)` resolve 后未清理，`check` 的 setTimeout 仍持续
  - 50ms 轮询在快速路由切换时创建大量定时器
  - 超时后未 reject，Promise resolve 后下游可能进入不一致
- **设计要点**:
  ```javascript
  if (!authStore.sessionReady) {
    await new Promise((resolve, reject) => {
      const start = Date.now()
      const timerIds = []
      const check = () => {
        if (authStore.sessionReady) {
          timerIds.forEach(clearTimeout)
          return resolve()
        }
        if (Date.now() - start > 15000) {
          timerIds.forEach(clearTimeout)
          return reject(new Error('Auth session timeout'))
        }
        timerIds.push(setTimeout(check, 50))
      }
      check()
    })
  }
  ```
- **依赖**:
  - 依赖：无
  - 被依赖：无
- **验收**:
  - 单元测试：模拟 sessionReady=true 立即 resolve，无 timer 泄漏
  - 单元测试：模拟 sessionReady=false 持续 15s，触发 reject
  - E2E：快速切换 5 个路由后，无 console 警告
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-013: traceId 升级到 crypto.randomUUID

- **描述**: 替换 [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) L92-L99 的 `Math.random()` 实现。
- **现状**:
  - 使用 `Math.random()`，**非密码学安全**
  - 注释错误地标注"UUIDv4 without crypto dependency"
  - 实际可使用 `crypto.randomUUID()`（所有现代浏览器支持）
- **影响**:
  - 安全：traceId 可猜测
  - 合规：可能被劫持追踪
- **设计要点**:
  ```javascript
  function generateTraceId() {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID()
    }
    // Fallback: 32 字符 hex
    const arr = new Uint8Array(16)
    window.crypto.getRandomValues(arr)
    return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('')
  }
  ```
- **验收**:
  - 1000 次生成的 traceId 全部唯一
  - 浏览器控制台 `window.crypto.randomUUID` 可用
  - Fallback 在旧浏览器可用
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-014: App.vue 重构为 script setup

- **描述**: 将 [src/App.vue](file:///d:/filework/excel-to-diagram/src/App.vue) L21-L62 从 Options API 改为 `<script setup>`。
- **现状**:
  - Options API 风格
  - `useAuthStore()` 在 `computed` 中调用（不规范）
  - `useMessage()` 在 method 中调用（与项目其他文件风格不一致）
  - `authEnabled: true` 硬编码
- **设计要点**:
  ```vue
  <script setup>
  import { ref, computed } from 'vue'
  import { useAuthStore } from './stores/authStore'
  import { useMessage } from './composables/useMessage'
  // ...
  const authEnabled = ref(true)
  const authStore = useAuthStore()
  const message = useMessage()

  function handleChangePasswordClose() {
    if (authStore.mustChangePassword) {
      message.warning('请先修改密码')
    }
  }
  </script>
  ```
- **依赖**:
  - 依赖：FR-025（错误边界）
  - 被依赖：无
- **验收**:
  - `vue/compiler-sfc` 无警告
  - 登录/登出/改密流程正常
  - 与现有 ESLint 规则兼容
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-015: main.js 启动序列重构

- **描述**: 解决 [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L88-L89 的 `loadFromCookie('restore')` 未 await 问题。
- **现状**:
  ```javascript
  const authStore = useAuthStore()
  authStore.loadFromCookie('restore')  // fire-and-forget
  app.mount('#app')  // 立即 mount
  ```
- **问题**:
  - 首次访问可能看到"未登录首页"一闪而过
  - 配合 App.vue 的 `v-if="!authStore.sessionReady"`，显示 spinner，但仍有 200-500ms 空白
- **设计要点**:
  ```javascript
  // 方案 A: 先 mount + spinner
  app.mount('#app')
  await useAuthStore().loadFromCookie('restore')

  // 方案 B: 用 Suspense + 异步 setup
  // <Suspense><template #default>...</template><template #fallback>...</template></Suspense>
  ```
- **依赖**:
  - 依赖：FR-014
  - 被依赖：FR-019（setOnUnauthorized 提前）
- **验收**:
  - 用户首次访问直接看到正确的登录态页面
  - 无"未登录首页"闪烁
  - E2E 测试通过
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-016: tabStore 持久化策略调整

- **描述**: tabStore 持久化从 sessionStorage 改为 localStorage，并过滤动态 label。
- **现状**:
  - [src/stores/tabStore.ts](file:///d:/filework/excel-to-diagram/src/stores/tabStore.ts) L128-L133 `storage: sessionStorage`
  - sessionStorage 在新标签页无法共享，**导致 tab 状态不一致**
  - tab.label 包含动态生成的 objectType 信息
- **设计要点**:
  ```typescript
  persist: {
    key: 'tab-store',
    storage: localStorage,  // 跨标签页
    paths: ['tabs', 'activeTabId'],
    serializer: {
      serialize: (state) => {
        const filtered = {
          ...state,
          tabs: state.tabs.map(t => ({
            ...t,
            label: t.meta?.isDetailRoute ? '' : t.label  // 动态 label 不持久化
          }))
        }
        return JSON.stringify(filtered)
      },
      deserialize: (str) => JSON.parse(str),
    }
  }
  ```
- **依赖**:
  - 依赖：FR-006（Pinia 持久化策略）
  - 被依赖：FR-007（keep-alive）
- **验收**:
  - 关闭浏览器后 tab 状态保留
  - 新标签页打开同一 URL，tab 状态一致
  - 动态 label 在恢复后重新生成
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-017: httpClient 引入请求去重

- **描述**: 多个组件同时挂载时，相同 URL+方法+body 复用同一个 Promise。
- **现状**:
  - [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js) 无去重
  - 列表页 N 个对象可能触发 N 次 GET
- **设计要点**:
  ```javascript
  const inflightCache = new Map()

  async function request(method, baseUrl, path, options = {}) {
    const cacheKey = `${method}:${baseUrl}${path}:${JSON.stringify(options.body || {})}`
    if (inflightCache.has(cacheKey) && !options.skipDedup) {
      return inflightCache.get(cacheKey)
    }
    const promise = doRequest(method, baseUrl, path, options)
    inflightCache.set(cacheKey, promise)
    promise.finally(() => inflightCache.delete(cacheKey))
    return promise
  }
  ```
- **依赖**:
  - 依赖：无
  - 被依赖：无
- **验收**:
  - 单元测试：并发 5 个相同请求，只发 1 个真实 HTTP 请求
  - 401 错误时清理 inflightCache
  - 可选 `skipDedup: true` 用于特殊场景
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-018: 路由配置模块化

- **描述**: 将 [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) L42-L227 的 200+ 行静态路由拆分。
- **现状**:
  - 单文件 200+ 行路由
  - 大量相似路由模板
  - `requiresAuth: true` 重复 15+ 次
  - 动态路由（`generateDynamicRoutes`）与静态路由混杂
- **设计要点**:
  ```
  src/router/
    index.js           # 主入口
    static-routes.js   # 静态路由
    dynamic-routes.js  # 动态路由（已有）
    route-helpers.js   # 共享元数据生成
  ```
  ```javascript
  // src/router/static-routes.js
  import { createAuthRoute } from './route-helpers'

  const routes = [
    createAuthRoute('/', 'landing', () => import('@/components/ArchWorkspaceNew.vue'), { title: '工作台' }),
    createAuthRoute('/system/archdata', 'ArchDataManagement', () => import('@/views/.../RelationshipManagement.vue'), { title: '架构数据管理' }),
    // ...
  ]
  ```
- **依赖**:
  - 依赖：FR-001（移除 console.log）
  - 被依赖：无
- **验收**:
  - 路由行为与重构前完全一致
  - 单文件不超过 200 行
  - E2E 路由测试全部通过
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-019: setOnUnauthorized 提前到 main.js 顶部

- **描述**: 避免 401 回调设置晚于 mount 导致的拦截失败。
- **现状**:
  - [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js) L81-L85 `setOnUnauthorized` 在 `app.use(ElementPlus)` 之后
  - `window.location.href` 硬跳转，丢失当前页面状态
- **设计要点**:
  ```javascript
  // src/main.js 顶部
  import { setOnUnauthorized } from './utils/api'
  setOnUnauthorized(() => {
    const currentPath = router.currentRoute.value.fullPath
    if (currentPath !== '/') {
      router.push({ path: '/', query: { reason: 'unauthorized', redirect: currentPath } })
    }
  })
  ```
- **验收**:
  - 401 触发软跳转（router.push）而非硬跳转（location.href）
  - 跳转后用户能看到 redirect 提示
  - 单元测试：模拟 401 后路由状态正确
- **优先级**: Could
- **来源**: 2026-06-07 代码审计

#### FR-020: 移除全局 \* 选择器 reset

- **描述**: 移除 [src/App.vue](file:///d:/filework/excel-to-diagram/src/App.vue) L67-L71 的 `* { margin: 0; padding: 0; box-sizing: border-box; }`。
- **现状**:
  - Universal Selector Reset 性能差（1000 节点表格增加重排成本）
  - 与 Element Plus 内部样式可能冲突
- **设计要点**:
  ```scss
  body, h1, h2, h3, h4, h5, h6, p, ul, ol, li, table, tr, td, th,
  form, fieldset, legend, input, button, select, textarea {
    margin: 0;
    padding: 0;
  }
  *, *::before, *::after {
    box-sizing: border-box;
  }
  ```
- **验收**:
  - 视觉与重构前一致（视觉回归测试）
  - 1000 节点表格首屏渲染耗时 < 200ms
  - Element Plus 组件样式正常
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-021: App.vue 添加错误边界

- **描述**: 用 `onErrorCaptured` 捕获子组件错误，避免整页崩溃。
- **现状**:
  - 错误只 push 到 `__appErrors`，无 UI 反馈
  - 局部组件错误导致整页崩溃
- **设计要点**:
  ```vue
  <script setup>
  import { onErrorCaptured, ref } from 'vue'
  const error = ref(null)
  onErrorCaptured((err, instance, info) => {
    error.value = { err, info, ts: Date.now() }
    logger.error('[ErrorBoundary]', err, info)
    return false  // 阻止向上传播
  })
  </script>
  ```
- **依赖**:
  - 依赖：FR-002（logger）
  - 被依赖：无
- **验收**:
  - 故意抛错的子组件不导致整页崩溃
  - 用户看到友好的错误提示
  - `__appErrors` 数组正确累积
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

***

### Group D: 清理与安全 \[4 项]

#### FR-022: 根目录临时文件清理

- **描述**: 清理 `d:\filework\` 根目录 200+ 临时文件。
- **现状**:
  - `analyze_*.py` 30+ 个
  - `check_*.py` 50+ 个
  - `fix_*.py` 40+ 个
  - `diag_*.log` 60+ 个
  - `test_*.txt` 80+ 个
  - `screenshot_*.png` 30+ 个
- **设计要点**:
  - 移到 `.archive/2026-06/` 目录
  - 加 `.gitignore` 规则
  - 添加 PowerShell 清理脚本 `scripts/cleanup-temp.ps1`
- **验收**:
  - 根目录 `*.py` `*.log` `*.txt` `*.png` 临时文件 < 10 个
  - 归档目录可搜索、可恢复
  - 不影响当前 build/test 流程
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-023: dev-login 生产环境禁用

- **描述**: 后端 `meta/api/auth_api.py` 的 `dev-login` 端点在生产环境返回 404。
- **现状**:
  - `GET /api/v1/auth/dev-login?username=admin` 无需密码
  - 当前有 `FLASK_ENV != 'production'` 检查，**但仅打印警告，不阻断**
- **设计要点**:
  ```python
  @app.route('/api/v1/auth/dev-login')
  def dev_login():
      if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('FLASK_PRODUCTION') == 'true':
          abort(404)
      # ...
  ```
- **依赖**:
  - 依赖：无
  - 被依赖：无
- **验收**:
  - `FLASK_ENV=production` 时，dev-login 返回 404
  - 开发环境仍可用
  - 单元测试覆盖两种环境
- **优先级**: Must
- **来源**: 2026-06-07 代码审计

#### FR-024: CORS 配置白名单

- **描述**: 后端 CORS 限制为已知 origin。
- **现状**:
  - dev 环境 CORS 允许所有 origin（`*`）
  - 生产环境可能继承
- **设计要点**:
  ```python
  CORS_ORIGINS = [
      'http://localhost:3004',
      'http://localhost:3010',
      # 生产环境域名
  ]
  ```
- **验收**:
  - 已知 origin 正常访问
  - 未知 origin 被拒绝
  - E2E 测试通过
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

#### FR-025: .env 文件 gitignore 与密钥管理

- **描述**: 确保敏感配置不被提交。
- **现状**:
  - `.env` `.env.local` `.env.production` 在 `.gitignore` 中（待验证）
  - JWT secret、DB path 可能硬编码
- **设计要点**:
  - 强化 `.gitignore`
  - 文档化密钥轮换流程
  - 引入 dotenv-vault 或类似方案（可选）
- **验收**:
  - `git log --all -- .env` 不显示真实密钥
  - `.gitignore` 包含所有敏感模式
- **优先级**: Should
- **来源**: 2026-06-07 代码审计

***

## 4. 非功能需求（NFR）

### NFR-001: 性能

- **描述**: 关键页面加载与交互性能指标
- **测量**:
  - 首屏 JS bundle (gzip): < 800KB（当前 \~1.5MB）
  - FCP: < 1.5s
  - LCP: < 2.5s
  - 路由切换: < 150ms
  - 1000 行表格滚动: 60fps
  - localStorage 大小: < 1MB
- **优先级**: Must
- **来源**: 业务目标

### NFR-002: 安全性

- **描述**: 关键安全属性
- **测量**:
  - traceId 用 crypto.randomUUID 不可猜测
  - dev-login 在生产环境返回 404
  - CORS 白名单生效
  - 无密钥泄露到 git
- **优先级**: Must
- **来源**: 安全审计要求

### NFR-003: 可观测性

- **描述**: 错误、警告、信息级别日志分级
- **测量**:
  - 生产环境无 console.log/warn
  - Vue 错误、Promise rejection、HTTP 4xx/5xx 上报到后端
  - logger.error 包含 traceId
- **优先级**: Should
- **来源**: 测试可观测性规范

### NFR-004: 可维护性

- **描述**: 仓库可读性
- **测量**:
  - 根目录临时文件 < 10 个
  - 路由文件 < 200 行
  - main.js import < 10 个
- **优先级**: Should
- **来源**: 业务目标

### NFR-005: 向后兼容

- **描述**: 重构不破坏现有功能
- **测量**:
  - 所有 E2E 测试通过
  - 现有 3100+ 单元测试通过
  - 旧 localStorage 数据兼容（或有迁移方案）
- **优先级**: Must
- **来源**: 业务目标

### NFR-006: 可回滚

- **描述**: 每个 FR 实施后可回滚
- **测量**:
  - git 分支保护
  - 关键改动通过 PR review
  - 蓝绿部署或 feature flag
- **优先级**: Must
- **来源**: 业务连续性

***

## 5. 外部接口需求（IF）

### IF-001: httpClient API 不变

- **类型**: API
- **入口**: `src/utils/httpClient.js`
- **要求**: `apiV1.get/post/put/delete/patch` `apiV2.*` 命名空间 API 签名保持
- **错误处理**: 内部优化对调用方透明

### IF-002: Element Plus 组件名不变

- **类型**: UI
- **入口**: 所有 .vue 文件
- **要求**: `el-button` `el-table` `el-input` 等组件名正常使用
- **约束**: 全量 → 按需不影响调用方

### IF-003: logger 替代 console

- **类型**: API
- **入口**: `src/utils/logger.js`
- **要求**: `logger.debug/info/warn/error` API 简单
- **迁移**: 全局替换 `console.*` → `logger.*`（可 ESLint 自动修复）

***

## 6. 过渡需求（TR）

### TR-001: localStorage 数据迁移

- **描述**: Pinia 持久化策略调整后，旧数据格式可能不兼容
- **策略**:
  - 启动时检测 `app-*` 键的 schema 版本
  - 不兼容时显示提示并重置
  - 提供 `scripts/migrate-localstorage.js` 手动迁移工具
- **回滚**: 删除 `app-*` 键即可恢复默认

### TR-002: Element Plus 全量 → 按需

- **描述**: 移除全量注册后，部分组件可能未通过 AutoImport 覆盖
- **策略**:
  - 第一阶段：保留全量 + 增加按需（重复加载但能跑）
  - 第二阶段：移除全量
  - 配套 E2E 全量回归
- **回滚**: 恢复 `app.use(ElementPlus)`

### TR-003: traceId 升级

- **描述**: 格式变化可能影响后端日志关联
- **策略**:
  - 新格式: UUID v4 (36 字符含连字符)
  - 旧格式: 32 字符 hex
  - 后端兼容两种格式（仅日志展示差异）
- **回滚**: 切换实现回 Math.random

***

## 7. 约束与假设

### 7.1 技术约束

- 必须保持 Vue 3 + Vite + Pinia 技术栈
- 必须保持 Element Plus 2.x（按需引入）
- 不能破坏现有 3100+ 单元测试
- 浏览器兼容：Chrome 100+ / Edge 100+（`crypto.randomUUID` 支持）
- 项目启动方式不变（`scripts/start.ps1`）

### 7.2 业务约束

- 不影响用户日常使用
- 不影响新功能开发
- 不强制一次性全量实施（可分里程碑）

### 7.3 假设

- 假设 1: dev-login 端点仅开发环境使用（**待确认 FR-023**）
- 假设 2: Element Plus 组件在 100+ 页面中只用 10-20 个高频组件（**待确认 FR-004**）
- 假设 3: traceId 仅用于日志关联，不参与鉴权（**已确认**）
- 假设 4: 单元测试 3100+ 不需要重写（**已确认**）

***

## 8. 优先级与里程碑建议

### 8.1 优先级总览

| FR     | 标题                     |   优先级  | 关联 NFR  | 工作量(估) |
| ------ | ---------------------- | :----: | ------- | -----: |
| FR-022 | 根目录临时文件清理              |  Must  | NFR-004 |  0.5 天 |
| FR-013 | traceId 升级             |  Must  | NFR-002 |  0.5 天 |
| FR-012 | 路由守卫 timer 清理          |  Must  | NFR-005 |    1 天 |
| FR-002 | 引入统一 logger            |  Must  | NFR-003 |    1 天 |
| FR-001 | 移除 console.log         |  Must  | NFR-003 |  0.5 天 |
| FR-023 | dev-login 禁用           |  Must  | NFR-002 |  0.5 天 |
| FR-004 | Element Plus 按需        |  Must  | NFR-001 |    2 天 |
| FR-005 | 虚拟滚动                   |  Must  | NFR-001 |    2 天 |
| FR-006 | Pinia 持久化策略            | Should | NFR-001 |    1 天 |
| FR-007 | keep-alive             | Should | NFR-001 |    1 天 |
| FR-014 | App.vue script setup   | Should | NFR-004 |  0.5 天 |
| FR-015 | 启动序列重构                 | Should | NFR-005 |    1 天 |
| FR-016 | tabStore 持久化           | Should | NFR-005 |    1 天 |
| FR-017 | httpClient 去重          | Should | NFR-001 |    1 天 |
| FR-018 | 路由模块化                  | Should | NFR-004 |    2 天 |
| FR-020 | 移除 \* 选择器              | Should | NFR-001 |  0.5 天 |
| FR-021 | 错误边界                   | Should | NFR-003 |    1 天 |
| FR-024 | CORS 白名单               | Should | NFR-002 |  0.5 天 |
| FR-025 | .env gitignore         | Should | NFR-002 |  0.5 天 |
| FR-011 | 样式入口合并                 | Should | NFR-001 |  0.5 天 |
| FR-003 | 错误上报                   | Should | NFR-003 |    2 天 |
| FR-009 | Vite 代理                |  Could | NFR-001 |  0.5 天 |
| FR-010 | SCSS additionalData    |  Could | NFR-001 |    1 天 |
| FR-008 | Element Plus locale 按需 |  Could | NFR-001 |  0.5 天 |
| FR-019 | setOnUnauthorized 提前   |  Could | NFR-005 |  0.5 天 |

### 8.2 建议里程碑（4 个）

#### 里程碑 M1: 紧急治理 (Week 1) — ✅ **已于 2026-06-07 完成**

- **范围**: Must 优先级 6 项（FR-022, FR-013, FR-012, FR-001+FR-002 合并, FR-023）
- **目标**: 修复安全风险 + 清理临时文件
- **风险**: 低（孤立改动）
- **可交付**: 全部达成 ✅
  - 根目录 < 10 个临时文件（从 277 → 6）
  - traceId 用 crypto.randomUUID
  - 路由守卫无 timer 泄漏
  - 生产构建无 console.log（4 核心文件 0 调用）
  - dev-login 在生产环境返回 404（10/10 单测）
- **实际产出**:
  - `src/utils/logger.js`（+ createLogger 工厂 API, 148 行）
  - `src/utils/__tests__/logger.spec.mjs`（15 单测全过）
  - `meta/tests/test_dev_login_prod.py`（10 单测全过）
  - `scripts/cleanup-temp.py`（258 文件归档, 716.3 MB → .archive/2026-06/）

#### 里程碑 M2: 性能核心 (Week 2-3) — ✅ **已于 2026-06-08 完成**

- **范围**: FR-004 + FR-005 + FR-006 + FR-007 + FR-011
- **目标**: 首屏加载 < 1s、列表流畅
- **风险**: 中（需全量回归测试）
- **可交付**: 全部达成 ✅
  - Element Plus 按需引入（per-component CSS 单独打包）
  - 1000 行表格 mount 6.0ms, DOM 节点 11（vs 之前 500+）
  - localStorage 持久化白名单化（4 store opt-in）
  - keep-alive max=10 启用（4 include + 3 exclude）
  - main.js 样式 6 → 1（index.scss 单入口）
- **实际产出**:
  - `src/components/common/MetaListV2/MetaListV2.vue` + 8 单测
  - `src/styles/index.scss`（合并 6 样式入口）
  - `src/main.js` 移除 app.use(ElementPlus)
  - `src/App.vue` 加 `<el-config-provider>` + `<keep-alive>`
  - 4 个 store 持久化升级到 v4 pick 语法

#### 里程碑 M3: 代码质量 (Week 4-5) — ⏳ **待启动**（建议 2026-06-15 后）

- **范围**: FR-014 + FR-015 + FR-016 + FR-017 + FR-018 + FR-020 + FR-021
- **目标**: 规范统一、减少技术债
- **风险**: 中（涉及多处重构）
- **可交付**:
  - App.vue 改 script setup
  - main.js 启动序列修复
  - tabStore 跨标签页一致
  - httpClient 去重生效
  - 路由文件模块化
  - 移除全局 \* 选择器
  - 错误边界生效
- **启动条件**:
  - M2 在线 1-2 周无回归
  - 用户确认 M2 性能可接受
  - M3 细化方案评审通过

#### 里程碑 M4: 可观测性与清理 (Week 6) — ⏳ **待启动**（建议 2026-06-29 后）

- **范围**: FR-003 + FR-008 + FR-009 + FR-010 + FR-019 + FR-024 + FR-025
- **目标**: 完善可观测、收尾清理
- **风险**: 低
- **可交付**:
  - 错误上报到后端（需新建 telemetry_api）
  - locale 按需加载
  - Vite 代理合并
  - SCSS additionalData 优化
  - CORS 白名单
  - .env gitignore 强化
- **依赖**: M3 完成后启动, 避免与 M3 改动冲突

### 8.3 实际进度 vs 计划

| 里程碑 | 计划 | 实际 | 偏差 |
|--------|------|------|------|
| M1 紧急治理 | Week 1 | 2026-06-07 (1 天) | 提前完成 ✅ |
| M2 性能核心 | Week 2-3 | 2026-06-08 (1 天) | 大幅提前 ✅ |
| M3 代码质量 | Week 4-5 | 待启动 | 按计划 ⏳ |
| M4 可观测性 | Week 6 | 待启动 | 按计划 ⏳ |

**注**: M1+M2 实际比计划提前 2-3 周, 主要因为:
1. 改动相对孤立,无重大外部依赖
2. 现有基础设施(SCSS、Vite、Vitest)成熟
3. 范围明确,无大范围需求变更

***

## 9. 变更/设计方案（RFC）

### 9.1 现状分析（按模块）

#### 9.1.1 [src/main.js](file:///d:/filework/excel-to-diagram/src/main.js)（91 行）

**当前实现**：

```javascript
// L8-L11: Element Plus 全量
import ElementPlus from 'element-plus'
import 'element-plus/theme-chalk/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

// L14-L29: 6 个样式文件
import './styles/tokens-yonyou.scss'
import './styles/variables.scss'
import './styles/element-variables.scss'
import './styles/element-plus-overrides.css'
import './styles/yon-ep.scss'
import './styles/_meta-table.scss'
import './style.css'

// L35-L38: Pinia 持久化（无 paths 限制）
pinia.use(createPersistedState({
  storage: localStorage,
  key: prefix => 'app-' + prefix,
}))

// L43-L70: 错误处理（仅 console）
app.config.errorHandler = (err, instance, info) => {
  // ... push to window.__appErrors
}

// L75-L79: 全量注册 Element Plus
app.use(ElementPlus, { locale: zhCn, size: 'default', zIndex: 3000 })

// L81-L85: setOnUnauthorized 在 app.use 之后
setOnUnauthorized(() => { window.location.href = '/?reason=unauthorized' })

// L88-L89: loadFromCookie fire-and-forget
authStore.loadFromCookie('restore')
app.mount('#app')
```

**现有问题**:

- Element Plus 全量（FR-004）
- 6 个样式同步（FR-011）
- Pinia 无 paths 限制（FR-006）
- 错误不上报（FR-003）
- setOnUnauthorized 时机晚（FR-019）
- loadFromCookie 未 await（FR-015）

**依赖**:

- 被 stores（authStore / tabStore 等）依赖
- 被 router 依赖（通过 stores）
- 被 App.vue 依赖（通过 stores）
- 被 utils/httpClient 依赖（通过 authStore）

#### 9.1.2 [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js)（347 行）

**当前实现**：

- L42-L227: 200+ 行静态路由
- L17-L40: `getDetailTabLabel` 含 4 处 `console.log`
- L249-L258: 轮询 timer 双重 resolve
- L304-L338: tab 状态管理逻辑（70+ 行）
- L241-L244: `ObjectDetail` 路由调 `validateDetailRoute`
- L297-L299: `isDetailRoute` 触发 `objectTypeService` 初始化

**现有问题**:

- console.log 残留（FR-001）
- 轮询 timer 未清理（FR-012）
- 路由硬编码（FR-018）

**依赖**:

- 依赖 stores（authStore, tabStore）
- 依赖 services（objectTypeService）
- 依赖 detailRouteGuard
- 依赖 dynamicRoutes
- 被 main.js 依赖
- 被 views/\*.vue 依赖

#### 9.1.3 [src/utils/httpClient.js](file:///d:/filework/excel-to-diagram/src/utils/httpClient.js)（375 行）

**当前实现**:

- L25-L42: ErrorCode 枚举
- L69-L87: 拦截器注册
- L92-L99: `generateTraceId` 用 `Math.random()`（FR-013）
- L104: 慢请求阈值 1000ms
- L120-L316: 核心 `request` 函数
- L321-L348: `apiV1` / `apiV2` 命名空间
- L362-L373: `downloadBlob` 工具

**现有问题**:

- traceId 弱随机（FR-013）
- 无请求去重（FR-017）
- 无重试机制
- 无缓存层

**依赖**:

- 依赖 utils/api.js
- 依赖 stores/authStore
- 被 services/*、views/* 大量依赖（约 50+ 文件）

#### 9.1.4 [src/stores/authStore.js](file:///d:/filework/excel-to-diagram/src/stores/authStore.js)（140 行）

**当前实现**:

- L11: `sessionReady` ref
- L19-L32: `isAdmin` computed（多源判断）
- L45-L67: `loadFromCookie` 合并 restore + fetchCurrentUser
- L118-L120: `getAuthHeaders` 永远返回 `{}`（Cookie 模式）

**现有问题**:

- 无明显问题（设计合理）
- `getAuthHeaders` 永远返回 `{}` 可能误导调用方

**依赖**:

- 依赖 services/authService
- 依赖 stores/userPreferences
- 被 router、App.vue、httpClient 依赖

#### 9.1.5 [src/stores/tabStore.ts](file:///d:/filework/excel-to-diagram/src/stores/tabStore.ts)（136 行）

**当前实现**:

- L18: `maxTabs = ref(10)` 硬编码
- L32-L35: 超 maxTabs 仅 `console.warn` 不处理
- L110: `hasOverflow` 阈值 8
- L128-L133: 持久化 sessionStorage

**现有问题**:

- 持久化 sessionStorage 跨标签页不一致（FR-016）
- maxTabs 硬编码
- 超限处理不优雅

**依赖**:

- 被 router/index.js 依赖
- 被 components/\* 依赖（TabBar 组件）

#### 9.1.6 [vite.config.js](file:///d:/filework/excel-to-diagram/vite.config.js)（63 行）

**当前实现**:

- L11-L16: AutoImport + Components + ElementPlusResolver
- L18-L20: `sourcemap: 'hidden'`
- L24-L48: 5 个代理规则（含 4 个 ws: true）
- L50-L57: SCSS additionalData 全量注入

**现有问题**:

- AutoImport 与全量注册冲突（FR-004）
- ws: true 滥用（FR-009）
- SCSS additionalData 全量（FR-010）

**依赖**:

- 被 build 流程依赖
- 被 dev 流程依赖

#### 9.1.7 [src/App.vue](file:///d:/filework/excel-to-diagram/src/App.vue)（105 行）

**当前实现**:

- L21-L62: Options API 风格
- L43-L46: `computed` 中调 `useAuthStore()`
- L67-L71: 全局 \* 选择器 reset

**现有问题**:

- Options API 风格不统一（FR-014）
- 全局 \* 选择器（FR-020）
- 缺错误边界（FR-021）

**依赖**:

- 被 main.js 依赖
- 依赖 components/\*
- 依赖 stores/authStore
- 依赖 composables/useMessage

### 9.2 目标状态

#### 9.2.1 main.js（重构后）

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createPersistedState } from 'pinia-plugin-persistedstate'
import router from './router'
import { setOnUnauthorized } from './utils/api'

// [NEW] 统一 logger
import { logger } from './utils/logger'

// [REMOVED] Element Plus 全量
// import ElementPlus from 'element-plus'
// import 'element-plus/theme-chalk/index.css'
// import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

// [MERGED] 单一样式入口
import './styles/index.scss'

// 持久化策略优化
const pinia = createPinia()
pinia.use(createPersistedState({
  storage: localStorage,
  key: prefix => 'app-' + prefix,
  paths: [
    'app.theme', 'app.locale',
    'sidebar.collapsed',
    'userPreferences.theme',
  ],
}))

const app = createApp(App)
app.use(pinia)
app.use(router)

// [MOVED] setOnUnauthorized 提前到顶部
setOnUnauthorized(() => {
  const currentPath = router.currentRoute.value.fullPath
  if (currentPath !== '/') {
    router.push({ path: '/', query: { reason: 'unauthorized', redirect: currentPath } })
  }
})

// 错误处理：上报 + logger
app.config.errorHandler = (err, instance, info) => {
  logger.error('[VueError]', err, { info, component: instance?.$?.type?.name })
  // push to __appErrors for backward compat
  window.__appErrors = window.__appErrors || []
  window.__appErrors.push({...})
}

// [REMOVED] 全量 Element Plus 注册
// app.use(ElementPlus, ...)

// [ADDED] 启动序列修复
const authStore = useAuthStore()
authStore.loadFromCookie('restore')  // 仍 fire-and-forget
app.mount('#app')
```

#### 9.2.2 路由（重构后）

```javascript
// src/router/static-routes.js
import { createAuthRoute, createAdminRoute } from './route-helpers'

const ROUTES = [
  createAuthRoute('/', 'landing', () => import('@/components/ArchWorkspaceNew.vue'), { title: '工作台' }),
  createAdminRoute('/system-admin', 'system-admin', () => import('@/views/SystemAdmin/index.vue'), { title: '日志管理' }),
  // ... 共 20+ 行
]

export default ROUTES
```

```javascript
// src/router/route-helpers.js
export function createAuthRoute(path, name, component, meta = {}) {
  return { path, name, component, meta: { requiresAuth: true, ...meta } }
}

export function createAdminRoute(path, name, component, meta = {}) {
  return createAuthRoute(path, name, component, { requiresAdmin: true, ...meta })
}
```

#### 9.2.3 httpClient（重构后）

```javascript
// [NEW] 使用 crypto.randomUUID
function generateTraceId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID()
  }
  const arr = new Uint8Array(16)
  window.crypto.getRandomValues(arr)
  return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('')
}

// [NEW] 请求去重
const inflightCache = new Map()

async function request(method, baseUrl, path, options = {}) {
  if (!options.skipDedup) {
    const cacheKey = `${method}:${baseUrl}${path}:${JSON.stringify(options.body || {})}`
    if (inflightCache.has(cacheKey)) {
      return inflightCache.get(cacheKey)
    }
    const promise = doRequest(method, baseUrl, path, options)
    inflightCache.set(cacheKey, promise)
    promise.finally(() => inflightCache.delete(cacheKey))
    return promise
  }
  return doRequest(method, baseUrl, path, options)
}
```

#### 9.2.4 vite.config.js（重构后）

```javascript
// [REMOVED] AutoImport 与全量注册的冲突解决
plugins: [
  vue(),
  AutoImport({
    resolvers: [ElementPlusResolver()],
  }),
  Components({
    resolvers: [ElementPlusResolver({ importStyle: 'sass' })],
  }),
],

server: {
  proxy: {
    '/api': { target: 'http://localhost:3010', changeOrigin: true },
    '/socket.io': { target: 'http://localhost:3010', changeOrigin: true, ws: true },
  }
},

css: {
  preprocessorOptions: {
    scss: {
      // [OPTIMIZED] 按需注入
      additionalData: (content, filename) => {
        if (filename.includes('components/') || filename.includes('views/')) {
          return `@use "@/styles/mixins.scss" as *;\n${content}`
        }
        return content
      }
    }
  }
},
```

### 9.3 详细设计

#### 9.3.1 logger 设计

```javascript
// src/utils/logger.js

const isDev = import.meta.env.DEV
const isProd = import.meta.env.PROD

function sendTelemetry(level, args) {
  if (!isProd) return
  try {
    const payload = {
      level,
      message: args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' '),
      traceId: window.__currentTraceId || null,
      ts: Date.now(),
      url: location.href,
    }
    navigator.sendBeacon('/api/v1/telemetry/error', JSON.stringify(payload))
  } catch (e) {
    // 上报失败静默
  }
}

export const logger = {
  debug: (...args) => isDev && console.debug('[DEBUG]', ...args),
  info: (...args) => isDev && console.info('[INFO]', ...args),
  warn: (...args) => console.warn('[WARN]', ...args),
  error: (...args) => {
    console.error('[ERROR]', ...args)
    sendTelemetry('error', args)
  },
}

export default logger
```

#### 9.3.2 请求去重设计

```javascript
// src/utils/httpClient.js 增量

const inflightCache = new Map()
const CACHE_CLEANUP_INTERVAL = 60000  // 1 分钟清理一次

// 定期清理过期项
setInterval(() => {
  if (inflightCache.size > 100) {  // 防止内存泄漏
    inflightCache.clear()
  }
}, CACHE_CLEANUP_INTERVAL).unref?.()  // Node 环境 unref

async function request(method, baseUrl, path, options = {}) {
  if (options.skipDedup) {
    return doRequest(method, baseUrl, path, options)
  }

  const cacheKey = `${method}:${baseUrl}${path}:${JSON.stringify(options.body || {})}`
  if (inflightCache.has(cacheKey)) {
    return inflightCache.get(cacheKey)
  }

  const promise = doRequest(method, baseUrl, path, options)
  inflightCache.set(cacheKey, promise)
  promise.catch(() => {}).finally(() => inflightCache.delete(cacheKey))
  return promise
}
```

#### 9.3.3 路由模块化设计

```
src/router/
├── index.js                 # 主入口（50 行）
├── route-helpers.js         # 共享元数据生成
├── static-routes/
│   ├── index.js             # 汇总
│   ├── arch-routes.js       # 架构数据相关
│   ├── admin-routes.js      # 管理员相关
│   ├── dev-routes.js        # 开发/测试路由
│   └── user-routes.js       # 用户相关
├── dynamic-routes.js        # 已有
└── detailRouteGuard.js      # 已有
```

#### 9.3.4 启动序列设计

```javascript
// src/main.js 启动序列
async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  pinia.use(createPersistedState({...}))
  app.use(pinia)
  app.use(router)
  
  // 1. 启动 401 拦截（第一时间）
  setOnUnauthorized(() => {...})
  
  // 2. 注册错误处理
  app.config.errorHandler = (err, instance, info) => {
    logger.error('[VueError]', err, { info, component: ... })
  }
  
  // 3. 挂载
  app.mount('#app')
  
  // 4. 异步恢复 session（不阻塞）
  const authStore = useAuthStore()
  authStore.loadFromCookie('restore').catch(err => {
    logger.warn('[AuthRestore] failed', err)
  })
}

bootstrap()
```

### 9.4 备选方案对比

| 决策点                 | 选定方案                 | 备选 A                 | 备选 B         | 决策理由                                  |
| ------------------- | -------------------- | -------------------- | ------------ | ------------------------------------- |
| Element Plus 引入     | 移除 app.use           | 保留全量 + 优化打包          | 完全手工 import  | 选 1：与 vite.config.js 现有 AutoImport 一致 |
| 虚拟滚动库               | el-table-v2          | vue-virtual-scroller | 自实现          | 选 1：与 Element Plus 生态一致               |
| Pinia 持久化           | localStorage + paths | sessionStorage（当前）   | 不持久化         | 选 1：跨标签页一致                            |
| keep-alive 启用       | 是                    | 否                    | 仅详情页         | 选 1：用户体验提升大                           |
| logger 实现           | 自实现                  | 引入 loglevel 等        | 仅替换 console  | 选 1：零依赖、可控                            |
| 错误上报                | navigator.sendBeacon | fetch                | 无（仅 console） | 选 1：异步非阻塞                             |
| 路由模块化               | 按业务拆分                | 按文件类型                | 保持单文件        | 选 1：易维护                               |
| SCSS additionalData | 函数式按需                | 全部移除                 | 全部保留         | 选 1：性能 + 兼容平衡                         |
| CORS 配置             | 白名单                  | 全允许                  | 仅生产          | 选 1：安全 + 开发体验平衡                       |

### 9.5 实施与迁移计划

#### 9.5.1 实施顺序

按里程碑 1-4 顺序执行（详见 §8.2）。

#### 9.5.2 风险缓解

| 风险                           |  概率 |  影响 | 缓解策略                            |
| ---------------------------- | :-: | :-: | ------------------------------- |
| Element Plus 按需遗漏组件          |  中  |  高  | E2E 全量回归；先双注册再移除全量              |
| traceId 升级影响后端               |  低  |  中  | 旧格式仅 32 字符，新格式 36 字符含连字符        |
| keep-alive 状态污染              |  中  |  中  | 配合 onActivated/onDeactivated 清理 |
| SCSS additionalData 移除导致样式丢失 |  中  |  中  | 函数式注入，先记录 404 警告                |
| 请求去重导致 401 错误传播              |  低  |  中  | 401 主动清理 inflightCache          |
| 启动序列修复导致白屏                   |  低  |  高  | 先 mount + spinner 模式            |
| CORS 白名单遗漏 origin            |  中  |  中  | 文档化所有 origin 列表                 |

#### 9.5.3 测试策略

- **单元测试**:
  - FR-013: traceId 唯一性测试
  - FR-012: timer 清理测试（mock setTimeout）
  - FR-017: 请求去重测试
  - FR-006: localStorage 大小监控测试
  - FR-023: dev-login 404 测试
  - FR-024: CORS 白名单测试
- **集成测试**:
  - FR-004: Element Plus 组件全量注册测试
  - FR-005: 虚拟滚动性能测试（1000 行 60fps）
  - FR-007: 路由切换耗时 < 200ms
  - FR-016: 跨标签页 tab 状态同步
  - FR-021: 错误边界不崩溃测试
- **E2E 测试**（Playwright）:
  - 现有 23 个 E2E 测试全量通过
  - 新增：根目录临时文件检查脚本
  - 新增：bundle size 断言

#### 9.5.4 回滚计划

| 阶段 | 回滚方式                                                 | 影响范围                            |
| -- | ---------------------------------------------------- | ------------------------------- |
| M1 | git revert 提交                                        | 仅 4-5 个文件                       |
| M2 | 恢复 `app.use(ElementPlus)`、移除 AutoImport 中部分 resolver | main.js / vite.config.js        |
| M3 | git revert 提交                                        | App.vue / router/\* / stores/\* |
| M4 | git revert 提交                                        | utils/\* / 后端 api/\*            |

每个里程碑独立可回滚，无需全部回退。

***

## 10. TBD 列表

| ID     | 项                                                | 缺失信息                                                                      | 下一步                                      |
| ------ | ------------------------------------------------ | ------------------------------------------------------------------------- | ---------------------------------------- |
| TBD-1  | dev-login 在生产环境的判断条件                             | 当前仅 `FLASK_ENV != 'production'`，是否需要额外检查 `FLASK_PRODUCTION` / `ENV_NAME`? | 与后端确认（FR-023）                            |
| TBD-2  | Element Plus 实际使用组件清单                            | 当前未知用了哪些组件，按需引入时需确认未遗漏                                                    | 用 `vite build --mode analyze` 分析（FR-004） |
| TBD-3  | keep-alive 与 tabStore 的协调                        | 启用 keep-alive 后 tabStore 的 activeTab 是否仍需要                                | 与 UI 设计确认（FR-007）                        |
| TBD-4  | 错误上报后端是否就绪                                       | `/api/v1/telemetry/error` 端点不存在，需新建                                       | 与后端协商（FR-003）                            |
| TBD-5  | CORS 白名单的 origin 列表                              | 生产环境域名未确定                                                                 | 与运维确认（FR-024）                            |
| TBD-6  | traceId 升级是否影响 SSE 事件关联                          | 当前 SSE 用 `?traceId=` 参数                                                   | 测试 SSE 流程（FR-013）                        |
| TBD-7  | SCSS additionalData 函数式注入的兼容性                    | Vite 5+ 才支持函数式参数                                                          | 确认 Vite 版本（FR-010）                       |
| TBD-8  | localStorage 数据迁移工具                              | 旧 `app-*` 键 schema 未知                                                     | 检查现有数据格式（TR-001）                         |
| TBD-9  | App.vue 改 script setup 后是否影响 dev-login cookie 设置 | `data()` 中的 `authEnabled` 在 setup 中如何表达                                   | 测试（FR-014）                               |
| TBD-10 | 启动序列修复后是否影响"重定向到原页面"功能                           | 修复后是否仍能正确处理 `?redirect=` 参数                                               | E2E 测试（FR-015）                           |

***

## 附录 A: 文件清单

### A.1 需要修改的文件

| 文件                             | FR                                                     | 影响                                        |
| ------------------------------ | ------------------------------------------------------ | ----------------------------------------- |
| src/main.js                    | FR-002, FR-003, FR-004, FR-006, FR-011, FR-015, FR-019 | 重构核心                                      |
| src/router/index.js            | FR-001, FR-012, FR-018                                 | 拆分 + 修复 timer                             |
| src/utils/httpClient.js        | FR-001, FR-013, FR-017                                 | 性能 + 安全                                   |
| src/utils/logger.js（新建）        | FR-002                                                 | 新建                                        |
| src/stores/tabStore.ts         | FR-016                                                 | 持久化策略                                     |
| src/App.vue                    | FR-014, FR-020, FR-021                                 | 重构                                        |
| src/styles/index.scss（新建）      | FR-011                                                 | 合并样式                                      |
| vite.config.js                 | FR-004, FR-009, FR-010                                 | 移除重复 ElementPlusResolver + 代理合并 + SCSS 优化 |
| meta/api/auth\_api.py          | FR-023                                                 | dev-login 强化                              |
| meta/server.py                 | FR-024                                                 | CORS 白名单                                  |
| .gitignore                     | FR-025                                                 | 强化环境文件忽略                                  |
| .archive/2026-06/（新建）          | FR-022                                                 | 归档临时文件                                    |
| scripts/cleanup-temp.ps1（新建）   | FR-022                                                 | 清理脚本                                      |
| meta/api/telemetry\_api.py（新建） | FR-003                                                 | 错误上报后端端点                                  |

### A.2 新建文件

| 文件                                                       | 用途        |
| -------------------------------------------------------- | --------- |
| src/utils/logger.js                                      | 统一 logger |
| src/styles/index.scss                                    | 样式合并入口    |
| src/router/route-helpers.js                              | 路由元数据工厂   |
| src/router/static-routes/index.js                        | 路由汇总      |
| src/router/static-routes/{arch,admin,dev,user}-routes.js | 路由分类      |
| scripts/cleanup-temp.ps1                                 | 临时文件清理    |
| meta/api/telemetry\_api.py                               | 错误上报后端    |
| docs/specs/spec-code-quality-perf-2026-06-07-v1.0.md     | 本 Spec    |

### A.3 涉及依赖文件（间接影响）

| 文件                                | 影响原因                                |
| --------------------------------- | ----------------------------------- |
| src/services/authService.js       | 被 httpClient 变化间接影响（去重缓存）           |
| src/services/objectTypeService.js | 被路由拆分影响（迁移到独立模块）                    |
| src/services/authService.js       | 调用 authStore.getAuthHeaders（API 稳定） |
| src/views/\*\*/\*.vue             | 100+ 视图文件，Element Plus 按需导入         |
| src/components/\*\*/\*.vue        | 50+ 组件文件，console.\* → logger.\*     |
| e2e/features/\*.spec.js           | E2E 测试，全量回归                         |
| meta/tests/\*\*/\*.py             | 单元测试（保持兼容）                          |

***

## 附录 B: 验收检查清单

### B.1 通用检查

- [ ] 所有 `console.*` 替换为 `logger.*`
- [ ] 生产构建无 console 输出（grep 验证）
- [ ] 开发环境保留 console 输出
- [ ] 所有 FR 有对应单元测试
- [ ] 现有 23 个 E2E 测试通过
- [ ] 现有 3100+ 单元测试通过
- [ ] 关键路径有集成测试

### B.2 性能检查

- [ ] 首屏 bundle (gzip) < 800KB
- [ ] FCP < 1.5s
- [ ] LCP < 2.5s
- [ ] 路由切换 < 150ms
- [ ] 1000 行表格滚动 60fps
- [ ] localStorage < 1MB

### B.3 安全检查

- [ ] traceId 不可猜测（crypto.randomUUID）
- [ ] dev-login 在生产环境 404
- [ ] CORS 白名单生效
- [ ] .env 文件未提交
- [ ] 无 console 泄露敏感信息

### B.4 可维护性检查

- [ ] 根目录临时文件 < 10 个
- [ ] main.js 样式 import < 5 个
- [ ] 路由文件 < 200 行
- [ ] 所有 .vue 用 `<script setup>`
- [ ] 无全局 \* 选择器

### B.5 可观测性检查

- [ ] Vue 错误上报到 `/api/v1/telemetry/error`
- [ ] Promise rejection 上报
- [ ] logger 输出包含 traceId
- [ ] 慢请求 > 1s 有警告
- [ ] 401 自动拦截

***

## 附录 C: 与历史 Spec 的关系

| Spec                                                                                                                                                             | 状态        | 与本 Spec 关系                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | -------------------------------------------- |
| [spec-code-quality-performance-optimization.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-code-quality-performance-optimization.md) v2.0 (2026-05-26) | 已完成 25+ 项 | 本 Spec 是其**后续治理轮次**，解决 2026-06-07 重新审计发现的新问题 |
| spec-state-management-enhancement.md                                                                                                                             | 已完成       | 与本 Spec FR-006/FR-016 关联                     |
| spec-v3-architecture-vs-implementation-todo.md                                                                                                                   | 进行中       | 与本 Spec 整体对齐                                 |

本 Spec **不重复** v2.0 已完成的项（如安全表达式、Cookie 认证、Pinia persist、拦截器补齐、BO 修复、N+1 优化、DRY 消除、硬编码消除、悲观锁、缓存精细化、日志分级、巨型类拆分、魔法值枚举化、CustomEvent 迁移、并发控制、深度模块化等），仅处理**新增**或**未完全根治**的问题。

***

## 附录 D: 后续工作

完成本 Spec 后，建议的下一轮治理方向：

1. **TypeScript 迁移**: 当前混合 .js/.ts/.vue
2. **Vue Query 引入**: 替代散落的 fetch + ref
3. **Storybook 建设**: 组件库文档化
4. **微前端探索**: 拆分 monorepo
5. **CDN 部署优化**: 静态资源走 CDN
6. **PWA 支持**: 离线缓存
7. **i18n 完善**: 提取多语言文案
8. **监控集成**: 接入 Sentry/Datadog

***

**Spec + RFC 包含 10 个章节,最后一节是 TBD 列表,内容完整。**

> **版本**: v1.0\
> **创建日期**: 2026-06-07\
> **下次评审**: 待用户确认

