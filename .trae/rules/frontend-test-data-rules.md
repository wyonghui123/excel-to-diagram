# 前端测试数据管理规范

> **智能体编写前端测试（单元测试 / E2E 测试）时必须遵循的测试数据管理规范。**
>
> **版本**: v3.19 | **更新**: 2026-06-11
>
> **配套文档**:
> - `e2e-simplification.md` - E2E 测试简化方案（v2 权威规范）
> - `frontend-testing-standards.md` - 前端测试标准规范
> - `test-data-rules.md` - 后端测试数据管理规范

---

## 一、核心原则

| 原则 | 说明 | 违反后果 |
|------|------|---------|
| **隔离性** | 每个测试创建自己的数据，测试后清理 | 数据污染，测试相互影响 |
| **幂等性** | `setupProductWithVersion()` 可多次调用，结果一致 | 重复创建数据 |
| **唯一性** | 使用时间戳/随机字符串避免 ID 冲突 | ID 冲突导致测试失败 |
| **可重现性** | 测试数据与环境无关，随时可运行 | 依赖特定 DB 状态 |

---

## 二、测试数据文件结构

```
src/test/
├── factories/                    # [NEW v3.19] 测试数据工厂
│   ├── index.js                 # 统一导出
│   ├── userFactory.js           # 用户工厂
│   └── productFactory.js        # 产品/版本工厂
├── fixtures/
│   ├── index.js                 # 统一导出
│   └── mockData.js              # Mock 数据模板
└── helpers/
    └── testDataSetup.js         # E2E 测试数据设置工具

e2e/helpers/
├── testDataSetup.js             # [NEW v3.19] E2E 测试数据核心模块
├── auth.js                      # 认证辅助函数（已导出 testDataSetup）
└── auto-fixtures.js             # v2 简化方案 fixtures
```

---

## 三、单元测试数据管理

### 3.1 使用 Mock 数据模板

**文件**：`src/test/fixtures/mockData.js`

```javascript
// [OK] 正确：使用 mockData 模板
import { mockUser, mockProduct, mockSuccessResponse } from '@/test/fixtures'

// 单个 mock
const user = mockUser()
const admin = mockUser({ role: 'admin', username: 'admin_test' })

// Mock API 响应
global.fetch.mockResolvedValueOnce(mockSuccessResponse(user))
```

**禁止做法**：

```javascript
// [X] 错误：硬编码数据
const user = { id: 1, username: 'test', role: 'user' }

// [X] 错误：在测试文件中重复定义 mock
const mockUser = {
  id: 1,
  username: 'test_user_1',
  display_name: 'Test User 1',
  // ... 重复定义
}
```

### 3.2 使用测试数据工厂

**文件**：`src/test/factories/`

```javascript
// [OK] 正确：使用工厂函数
import { createUser, createProduct } from '@/test/factories'

// 生成测试用户
const user = createUser()  // 自动生成唯一 ID、时间戳
const admin = createUser({ role: 'admin' })

// 生成测试产品
const product = createProduct({ name: 'Test Product' })
```

### 3.3 单元测试 Mock 数据示例

```javascript
// src/stores/__tests__/authStore.spec.js
import { mockUser, mockSuccessResponse } from '@/test/fixtures'
import { mockResponse } from '@/test/fixtures'

describe('authStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch user profile', async () => {
    const mockUserData = mockUser({ username: 'test_user' })
    global.fetch.mockResolvedValueOnce(
      mockResponse({ success: true, data: mockUserData })
    )

    const store = useAuthStore()
    await store.fetchProfile()

    expect(store.user).toEqual(mockUserData)
  })

  it('should handle fetch error', async () => {
    global.fetch.mockResolvedValueOnce(
      mockResponse({ message: 'Unauthorized' }, false, 401)
    )

    const store = useAuthStore()
    await store.fetchProfile()

    expect(store.error).toBeTruthy()
  })
})
```

---

## 四、E2E 测试数据管理

### 4.1 核心函数：ensureProductWithVersion()

**文件**：`e2e/helpers/testDataSetup.js`

```javascript
// [OK] 正确：自动创建测试数据
import { ensureProductWithVersion, runCleanup } from '../helpers/auth.js'

test('C05: 架构数据列表测试', async ({ page }) => {
  // 自动确保测试数据存在，不会跳过测试
  const pv = await ensureProductWithVersion(page)
  console.log(`测试数据: product=${pv.product.id}, version=${pv.version.id}`)

  // 直接导航到页面
  await page.goto(`/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`)

  // ... 测试逻辑 ...
})

// 测试后自动清理
test.afterEach(async () => {
  await runCleanup()
})
```

### 4.2 禁止做法

```javascript
// [X] 错误：依赖 findProductWithVersion 可能返回 null
const pv = await findProductWithVersion(page)
if (!pv) {
  test.skip()  // 测试被跳过！
}

// [X] 错误：硬编码产品名称
await page.goto('/system/archdata?productId=1&versionId=1')

// [X] 错误：不清理测试数据
const boCode = `E2E_BO_${Date.now()}`
await api.createBusinessObject({ code: boCode })
// 测试结束不清理 → DB 垃圾
```

### 4.3 完整测试数据 Setup

```javascript
// 创建完整层级数据（domain -> sub_domain -> service_module -> business_object）
import { setupCompleteArchData, runCleanup } from '../helpers/auth.js'

test('C10: 完整 CRUD 测试', async ({ page }) => {
  // 创建完整测试数据
  const testData = await setupCompleteArchData(page)
  // {
  //   product: { id, name, ... },
  //   version: { id, name, ... },
  //   domain: { id, name, ... },
  //   subDomain: { id, name, ... },
  //   serviceModule: { id, name, ... },
  //   businessObject: { id, name, ... }
  // }

  // 使用 URL 参数直接导航
  await page.goto(
    `/system/archdata?productId=${testData.product.id}&versionId=${testData.version.id}&tab=business_object`
  )

  // ... 测试逻辑 ...
})

test.afterEach(async () => {
  await runCleanup()  // 自动清理所有创建的数据
})
```

---

## 五、智能体编写测试规范

### 5.1 单元测试编写规范

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | import Mock 数据 | `import { mockUser, mockProduct, mockSuccessResponse } from '@/test/fixtures'` |
| 2 | Mock API 响应 | `global.fetch.mockResolvedValueOnce(mockSuccessResponse(mockUser()))` |
| 3 | 验证业务逻辑 | `expect(store.user).toEqual(...)` |

**标准模板**：

```javascript
/**
 * {ComponentName} 组件测试
 *
 * [测试数据规范 v3.19]
 * - 使用 @/test/fixtures/mockData 的 Mock 模板
 * - 禁止硬编码测试数据
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { mockUser, mockSuccessResponse, mockErrorResponse } from '@/test/fixtures'

describe('{ComponentName}', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render user data', async () => {
      const user = mockUser({ username: 'test_user' })
      global.fetch.mockResolvedValueOnce(mockSuccessResponse(user))

      const wrapper = mount({ComponentName}, {
        props: { userId: 1 }
      })

      expect(wrapper.text()).toContain('test_user')
    })
  })

  describe('error handling', () => {
    it('should handle API error', async () => {
      global.fetch.mockResolvedValueOnce(mockErrorResponse('Not found', 404))

      const wrapper = mount({ComponentName}, {
        props: { userId: 999 }
      })

      expect(wrapper.text()).toContain('Error')
    })
  })
})
```

### 5.2 E2E 测试编写规范

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 解构 fixtures | `import { test, expect } from '../helpers/auto-fixtures.js'` |
| 2 | 获取测试数据 | `const pv = await ensureProductWithVersion(page)` |
| 3 | 使用 URL 参数导航 | `page.goto(\`/path?productId=${pv.product.id}&versionId=${pv.version.id}\`)` |
| 4 | 添加 afterEach 清理 | `test.afterEach(async () => { await runCleanup() })` |

**标准模板**：

```javascript
/**
 * SXX: 场景名称 - 功能测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 *
 * [测试数据规范 v3.19]
 * - 使用 ensureProductWithVersion() 确保测试数据存在
 * - 使用 runCleanup() 测试后自动清理
 * - 禁止硬编码产品/版本 ID
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { ensureProductWithVersion, runCleanup } from '../helpers/auth.js'

test.describe('SXX: 场景名称', () => {
  // [NEW v3.19] 每个测试后自动清理
  test.afterEach(async () => {
    await runCleanup()
  })

  test('C01: 测试用例名称', async ({ page }, testInfo) => {
    // [NEW v3.19] 使用 ensureProductWithVersion 确保测试数据
    const pv = await ensureProductWithVersion(page)
    console.log(`测试数据: product=${pv.product.id}, version=${pv.version.id}`)

    // 使用 URL 参数直接导航
    await page.goto(
      `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`,
      { waitUntil: 'domcontentloaded' }
    )
    await page.waitForTimeout(2000)

    // ... 测试逻辑 ...
  })
})
```

---

## 六、禁止行为清单

| # | 禁止 | 正确做法 | 严重程度 |
|---|------|---------|---------|
| 1 | 硬编码 `productId=1` | 使用 `ensureProductWithVersion()` | 严重 |
| 2 | `findProductWithVersion()` 返回 null 后跳过测试 | 使用 `ensureProductWithVersion()` 自动创建 | 严重 |
| 3 | 不清理测试数据 | 使用 `runCleanup()` 或 `isolation.createTracked()` | 严重 |
| 4 | 在测试文件中重复定义 mock | 使用 `@/test/fixtures/mockData` | 中等 |
| 5 | 使用 `Date.now()` 命名测试数据 | 使用 `ensureProductWithVersion()` 或工厂函数 | 中等 |
| 6 | E2E 测试硬编码 `page.goto('/path')` | 使用 URL 参数 `?productId=X&versionId=Y` | 中等 |

---

## 七、快速参考卡片

### 单元测试

```javascript
// 导入 Mock 数据
import { mockUser, mockProduct, mockSuccessResponse, mockErrorResponse } from '@/test/fixtures'

// Mock API
global.fetch.mockResolvedValueOnce(mockSuccessResponse(mockUser()))

// 验证
expect(result).toEqual(mockUser())
```

### E2E 测试

```javascript
// 导入数据管理函数
import { ensureProductWithVersion, runCleanup } from '../helpers/auth.js'

// 获取测试数据（自动创建）
const pv = await ensureProductWithVersion(page)

// 使用 URL 参数导航
await page.goto(`/path?productId=${pv.product.id}&versionId=${pv.version.id}`)

// 测试后清理
test.afterEach(async () => { await runCleanup() })
```

---

## 八、相关文件索引

| 文件 | 说明 | 规范类型 |
|------|------|---------|
| `src/test/factories/userFactory.js` | 用户测试数据工厂 | 实现 |
| `src/test/factories/productFactory.js` | 产品测试数据工厂 | 实现 |
| `src/test/fixtures/mockData.js` | Mock 数据模板 | 实现 |
| `e2e/helpers/testDataSetup.js` | E2E 测试数据核心模块 | 实现 |
| `e2e/helpers/auth.js` | 认证辅助（已导出 testDataSetup） | 实现 |
| `.trae/rules/frontend-testing-standards.md` | 前端测试标准 | 规范 |
| `.trae/rules/e2e-simplification.md` | E2E 简化方案 | 规范 |
| `.trae/rules/test-data-rules.md` | 后端测试数据管理 | 规范 |

---

## 九、修改日志

| 日期 | 修改 | 作者 |
|------|------|------|
| 2026-06-11 | 创建本文档（基于测试数据优化工作） | AI Assistant |

---

_本文档是前端测试数据管理的权威规范，所有智能体编写前端测试前必须阅读并遵守_
