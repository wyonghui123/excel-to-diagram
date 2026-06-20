# 前端 E2E 测试简化方案 - 强制规范 [NEW 2026-06-05]

> [!!!] 本文件是 E2E 测试的**新方案单一事实源** [!!!]
> [!!!] 与 `.trae/rules/e2e-testing.md` 配套使用，本文件优先 [!!!]
> [!!!] 所有 Agent 写 E2E 测试前必须阅读本文件 [!!!]

> **背景**：v1 时代测试样板代码 70%、登录重复 5-15s/测试、Date.now() 命名 + 不清理导致 DB 几百条垃圾。
> **新方案**：通过 6 维度优化，登录开销归零、代码量 -46%、脏数据 0、可观测性 +70%。

---

## 一、8 条新铁律（违反 = 测试无效或产生脏数据）

| # | 铁律 | 违规后果 | 正确做法 |
|---|------|---------|---------|
| 1 | **新测试必须 import 自 `auto-fixtures.js`** | 重复登录、重复设权限 | `import { test, expect } from '../helpers/auto-fixtures.js'` |
| 2 | **禁止再写 `login(page)`** | 浪费 5-15s/测试 × N | 用 `global-setup.js` 共享 storageState |
| 3 | **禁止硬编码 `Date.now()` 命名测试数据** | 跑 100 轮后 DB 几百条垃圾 | 用 `isolation.createTracked(type, data)` + UUID |
| 4 | **禁止直接 `page.goto()`** | 页面未加载完就操作 | 用 `navigateTo(page, path, opts)` |
| 5 | **禁止直接 `page.locator('.el-table...')`** | UI 一改全挂 | 用 POM：`new ArchDataPage(page).expectRowExists(code)` |
| 6 | **禁止 `waitForTimeout(N)`** | 慢 + 不稳定 | 用 `waitForApiFn(page, 'GET /api/xxx')` |
| 7 | **业务操作必须用 `withStep()` 包裹** | 失败时不知道哪一步出错 | `await withStep(page, testInfo, 'name', async () => {...})` |
| 8 | **每个测试必须用 `isolation` fixture** | 不清理 → 脏数据累积 | `{ isolation }` from auto-fixtures，自动 afterEach 清理 |

**例外**：smoke 测试（`e2e/smoke/*.smoke.spec.js`）可以保留 `login()` 写法，因为 smoke 假设 0 前置状态。

---

## 二、强制 import 模板（每个新 .spec.js 必须用）

```javascript
/**
 * SXX: 场景名称 - 功能测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 必须 import 自 auto-fixtures.js（新方案）
 * - 必须用 isolation.createTracked() 创建测试数据
 * - 必须用 withStep() 包裹每个业务步骤
 * - 详细: .trae/rules/e2e-simplification.md（本文件）
 */
import { test, expect } from '../helpers/auto-fixtures.js'  // ← 注意不是 @playwright/test
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'  // ← 按需 import POM

test.describe('SXX: 场景名称', () => {
  test('C01: 测试用例', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn  // ← 解构 fixtures
  }, testInfo) => {
    // 1. 数据准备（智能查找 + 自动跟踪）
    const pv = await dataFinder.productWithVersion()

    // 2. 导航（智能等版本上下文恢复）
    await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)

    // 3. 业务操作（每个步骤都有截图 + 错误捕获）
    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到业务对象 tab', async () => {
      await archData.openTab('businessObject')
    })

    // 4. 创建测试数据（自动跟踪 → 测试结束自动清理）
    const boCode = `E2E_${Date.now().toString(36).toUpperCase()}`
    await withStep(page, testInfo, 'API 创建业务对象', async () => {
      await isolation.createTracked('business_object', {
        code: boCode, name: `测试对象_${boCode}`, version_id: pv.version.id
      })
    })

    // 5. 验证（智能重试 + onRetry 触发刷新）
    await withStep(page, testInfo, '验证列表中出现', async () => {
      await archData.expectRowExists(boCode, {
        timeout: 20000,
        onRetry: async () => { await archData.search('') }  // 找不到时触发刷新
      })
    })

    // 不用手动清理 - afterEach 自动调用 isolation.cleanup()
  })
})
```

**禁止使用**（v1 模式，已废弃）：

```javascript
// [X] 错误：直接 import @playwright/test
import { test, expect } from '@playwright/test'

// [X] 错误：每个测试都登录
await login(page)
await setAdminPermissions(page)

// [X] 错误：硬编码 Date.now() 命名 + 不清理
const boCode = `E2E_BO_${Date.now()}`
// ... 测试结束不清理 → DB 垃圾

// [X] 错误：直接 locator
await page.locator('.el-table__body tr:has-text("xxx")').click()

// [X] 错误：page.goto
await page.goto('/system/archdata')
await page.waitForTimeout(2000)
```

---

## 三、Fixtures 速查（`helpers/auto-fixtures.js`）

| Fixture | 类型 | 用途 | 示例 |
|---------|------|------|------|
| `page` | Page | 浏览器页面（自带 auth） | `await page.locator(...)` |
| `navigateTo` | Function | 智能导航（带版本上下文恢复） | `await navigateTo(page, '/path?productId=1')` |
| `dataFinder` | DataFinder | 智能数据查找/创建（30s 缓存） | `await dataFinder.productWithVersion()` |
| `isolation` | TestIsolation | 测试数据跟踪 + 自动清理 | `await isolation.createTracked('business_object', {...})` |
| `waitForApiFn` | Function | 基于 API 响应等待 | `await waitForApiFn(page, 'GET /api/v2/bo/business_object')` |
| `withScreenshot` | Function | 自动截图（步骤级） | `await withScreenshot(page, testInfo, 'name', fn)` |

---

## 四、POM 速查（`page-objects/`）

| POM | 适用页面 | 核心方法 |
|-----|---------|---------|
| `GenericListPage` | 任何列表页 | `expectRowExists` / `expectRowNotExists` / `search` / `clickToolbarButton` |
| `ArchDataPage` | `/system/archdata` | `openTab` / `expectRowExists` / `search` / 继承自 GenericListPage |
| `DetailDrawerPage` | 详情抽屉 | `waitForOpen` / `clickEdit` / `clickDelete` / `confirmDelete` / `expectSuccessMessage` |

**通用方法（`GenericListPage`）**：

```javascript
// 智能查找行（带 polling + onRetry）
await listPage.expectRowExists(text, {
  timeout: 20000,
  pollInterval: 1000,
  onRetry: async () => { await listPage.search('') }
})

// 断言行不存在
await listPage.expectRowNotExists(text, { timeout: 10000 })

// 搜索
await listPage.search(keyword)
```

---

## 五、TestIsolation 速查（`helpers/test-isolation.js`）

```javascript
// 创建并自动注册
const bo = await isolation.createTracked('business_object', {
  code: 'E2E_xxx', name: '测试', version_id: 2
})
// → API 调用 + 自动 track(type, id)
// → 测试结束自动 cleanup()

// 查询已跟踪对象
const tracked = isolation.getTracked('business_object')

// 标记已手动清理（避免 cleanup 重复删除）
isolation.markCleaned('business_object')
```

**支持类型**（在 `_apiUrlForType` 中映射）：
- `business_object` → `/api/v2/bo/business_object`
- `relationship` → `/api/v2/bo/relationship`
- 新增类型：在 `_apiUrlForType(type, id)` 中加 case

---

## 六、global-setup + storageState 工作原理

```
playwright.config.js
└── globalSetup: './e2e/helpers/global.setup.js'
    ↓
    启动时执行 1 次：登录 admin → 写 e2e/.auth/admin.json
    ↓
    所有 project 自动加载 .auth/admin.json 作为初始 cookie
    ↓
    每个测试无需重新登录 [OK]
```

**路径规范**：
- `e2e/.auth/admin.json` — admin 认证态（**git 忽略**）
- `e2e/.auth/readonly.json` — readonly 认证态（可选）
- `e2e/helpers/global.setup.js` — 生成脚本

---

## 七、添加新测试的标准流程

### 7.1 写新 features 测试

1. **复制模板**（参考 `e2e/features/arch-data-crud-v2.spec.js`）
2. **修改 import 路径**（用 `auto-fixtures.js`）
3. **解构 fixtures**：`{ page, navigateTo, dataFinder, isolation, waitForApiFn }`
4. **业务逻辑**：每个步骤 `withStep` 包裹
5. **测试数据**：用 `isolation.createTracked` 创建，**禁止 Date.now() + 不清理**
6. **POM**：用 `new XxxPage(page)` 操作，**禁止直接 locator**

### 7.2 添加新的 POM 类

1. **新文件**：`e2e/page-objects/XxxPage.js`
2. **继承**：`export class XxxPage extends GenericListPage { ... }`
3. **导出**：`e2e/page-objects/index.js`
4. **写测试**：`new XxxPage(page).method(...)`

### 7.3 添加新的可隔离类型

1. **修改**：`e2e/helpers/test-isolation.js` 的 `_apiUrlForType(type, id)`
2. **验证**：用 `isolation.createTracked('new_type', {...})` 测试

---

## 八、v1 → v2 迁移清单

| v1 旧模式 | v2 新模式 | 必改 |
|---------|---------|------|
| `import { test } from '@playwright/test'` | `import { test } from '../helpers/auto-fixtures.js'` | [OK] |
| `await login(page)` + `setAdminPermissions(page)` | 删除（global-setup 已处理） | [OK] |
| `await page.goto(url)` + `waitForTimeout` | `await navigateTo(page, url)` | [OK] |
| `const boCode = \`E2E_${Date.now()}\`` + 不清理 | `isolation.createTracked('business_object', {...})` | [OK] |
| `page.locator('.el-table...')` | `new ArchDataPage(page).method()` | [OK] |
| `await waitForTimeout(2000)` | `await waitForApiFn(page, 'GET /api/...')` | [OK] |
| `await test.step('name', fn)` | `await withStep(page, testInfo, 'name', fn)` | [OK] |
| `await getAuthHeaders(page)` + `page.request` | `await isolation.createTracked()` 内部已处理 | [OK] |

**已迁移示例**：`e2e/features/arch-data-crud-v2.spec.js`（80 行 vs 原版 148 行）

---

## 九、与其他规则文件的关系

| 文件 | 关系 |
|------|------|
| `.trae/rules/SESSION_REMINDER.md` | 入口，引用本文件 |
| `.trae/rules/e2e-testing.md` | v1 时代规则（部分仍有效） |
| `.trae/rules/e2e-simplification.md` | **本文件**，v2 新方案权威规范 |
| `.trae/rules/frontend-test-auth.md` | 认证细节（dev-login cookie） |
| `.trae/rules/frontend-test-data-rules.md` | **测试数据管理规范**（v3.19 新增） |
| `.trae/rules/page-health-rules.md` | 页面健康检查 |
| `.trae/rules/multi-agent-coordination.md` | 多 Agent 端口/资源隔离 |

**优先级**：`e2e-simplification.md` > `e2e-testing.md`（新方案优先）

---

## 九点五、测试数据规范（v3.19 新增）

> **所有 E2E 测试必须遵循测试数据管理规范，确保测试隔离和自动清理。**

### 核心规则

| 规则 | 说明 | 正确做法 |
|------|------|---------|
| **数据获取** | 使用 `ensureProductWithVersion()` | 自动创建测试数据，不会跳过测试 |
| **数据清理** | 使用 `runCleanup()` | 测试后自动清理，避免 DB 污染 |
| **禁止硬编码** | 不使用 `productId=1` | 使用 URL 参数 `?productId=${pv.product.id}` |

### 标准测试模板

```javascript
import { test, expect } from '../helpers/auto-fixtures.js'
import { ensureProductWithVersion, runCleanup } from '../helpers/auth.js'

test.describe('SXX: 场景名称', () => {
  // [NEW v3.19] 每个测试后自动清理
  test.afterEach(async () => {
    await runCleanup()
  })

  test('C01: 测试用例', async ({ page }) => {
    // [NEW v3.19] 确保测试数据存在
    const pv = await ensureProductWithVersion(page)

    // 使用 URL 参数导航
    await page.goto(
      `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`,
      { waitUntil: 'domcontentloaded' }
    )

    // ... 测试逻辑 ...
  })
})
```

### 禁止行为

| 禁止 | 后果 |
|------|------|
| `findProductWithVersion()` 返回 null 后 `test.skip()` | 测试被跳过，无法验证功能 |
| 硬编码 `productId=1, versionId=1` | 数据可能不存在或已被删除 |
| 创建数据后不清理 | DB 污染，测试数据累积 |

---

## 十、强制实施检查清单（Agent 写完测试后自查）

```
[ ] import 来自 auto-fixtures.js？
[ ] 没有 login() / setAdminPermissions()？
[ ] 没有 page.goto() 直接调用？
[ ] 没有 Date.now() 硬编码命名 + 不清理？
[ ] 没有直接 page.locator('.el-table...')？
[ ] 没有 waitForTimeout() 硬编码等待？
[ ] 每个业务步骤都有 withStep()？
[ ] isolation fixture 已解构（用 cleanup 自动清理）？
[ ] POM 已 import（用 class 操作，不直接 locator）？
```

**全部打钩 = 符合新方案规范** [OK]

---

## 十一、修改日志

| 日期 | 修改 | 作者 |
|------|------|------|
| 2026-06-05 | 创建本文档（基于 v2 实施报告） | Test Simplifier Agent |
| 2026-06-05 | 强制规范：从可选 → 必选 |  |

---

_本文件是 v2 简化方案的权威规范，所有 Agent 写 E2E 测试前必须阅读并遵守_
