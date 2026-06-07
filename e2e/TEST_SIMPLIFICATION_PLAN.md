# 前端测试深度简化方案（6 维度）

> 基于 `playwright.config.js` + `e2e/helpers/*` + `e2e/features/*` 现状
> 目标：测试代码量 -50%、执行时间 -60%、失败定位时间 -70%

## 现状分析（已观察到的问题）

| # | 痛点 | 影响 | 出现频率 |
|---|------|------|---------|
| 1 | 每个测试都 `login()` + `setAdminPermissions()` | +3-5s/测试，10 个测试 = 30-50s 浪费 | 25+ 个 features 测试 |
| 2 | 每个测试都 `navigateAndWaitForPage()` + `waitForTimeout(1500)` | +1.5-2s/测试 | 几乎所有 |
| 3 | 每个测试都 `findProductWithVersion()` 查询数据 | 5-10 次 API 调用/测试 | 80% 测试 |
| 4 | 同一个 URL 路径硬编码在 25+ 个文件 | 改 URL 要改 25 个地方 | 全部 |
| 5 | 硬编码 `Date.now()` 命名 + 不清理 → DB 脏数据累积 | 跑 100 次后列表里有几百个 E2E_xxx_xxxx | 80% |
| 6 | 失败时只看截图，不知道具体哪一步出错 | 排查 5-10 分钟 | 100% |
| 7 | 复制粘贴的 `openRowDetailByCode`、`switchTab` 等 helper | 散落各文件 5+ 份副本 | 60% |

## 6 维度简化方案

### 维度 1：Page Object Model（POM）—— **代码量 -50%**

**问题**：所有测试都直接 `page.locator('.el-table__body tr:has-text("xxx")').click()`，UI 一改全挂。

**方案**：把每个高频页面抽象成类，封装选择器和常用操作。

```javascript
// e2e/page-objects/ArchDataPage.js
export class ArchDataPage {
  constructor(page) { this.page = page }
  
  async openTab(name) { ... }              // 切 tab
  async openDetailByCode(code) { ... }     // 点击行打开 drawer
  async clickEdit() { ... }                // drawer 内点编辑
  async fillField(name, value) { ... }     // 字段填写
  async clickSave() { ... }
  async clickDelete() { ... }
  async confirmDelete() { ... }
  async expectSuccessMessage() { ... }
  async expectInList(code) { ... }
  async expectNotInList(code) { ... }
}
```

**收益**：测试变成业务描述（`.clickEdit().fillField('name', x).clickSave().expectInList(x)`）

### 维度 2：菜单驱动导航 —— **真实用户路径 + 改 URL 不用改 25 文件**

**问题**：URL 散落 25 个文件，改一个菜单要改 25 处。

**方案**：通过菜单文本点击导航（真实用户行为），自动获取真实 URL。

```javascript
// e2e/helpers/menu-navigator.js
export class MenuNavigator {
  // 从侧边栏菜单点击 "产品管理"，自动到达对应 URL
  async navigateByMenuText(text) { ... }
  
  // 通过面包屑反向定位
  async getCurrentBreadcrumb() { ... }
}
```

### 维度 3：测试隔离 + 自动清理 —— **解决脏数据**

**问题**：`Date.now()` 命名的数据用完不清理，10 轮测试后几百个 E2E_BO_xxxx。

**方案**：
- **每测试 UUID 命名**（不是 `Date.now()`）
- **afterEach 自动清理**用 `trackedIds` 注册的所有数据
- **DB 快照**：测试前快照，测试后可选恢复

```javascript
// e2e/helpers/test-isolation.js
export class TestIsolation {
  track(testId, type) { ... }   // 注册要清理的对象
  async cleanup() { ... }       // afterEach 调用
}
```

### 维度 4：自动截图 + Trace + 健康报告 —— **失败定位 -70%**

**问题**：测试失败时只有 1 张截图，不知道哪步出错。

**方案**：
- **test.step 包装**：每个 step 自动截图
- **失败时自动打 zip 包**（截图 + trace + 错误日志 + 网络请求）
- **健康检查集成**：pageerror/console.error 自动记录到结果

```javascript
// e2e/helpers/auto-trace.js
export async function withStep(page, testInfo, name, fn) {
  console.log(`[STEP] ${name} START`)
  await page.screenshot({ path: `traces/${name}-before.png` }).catch(()=>{})
  try {
    const result = await fn()
    console.log(`[STEP] ${name} OK`)
    return result
  } catch (e) {
    await page.screenshot({ path: `traces/${name}-FAIL.png` }).catch(()=>{})
    throw e
  }
}
```

### 维度 5：API 智能等待 + 网络拦截 —— **执行时间 -30%**

**问题**：测试中等后端响应，`waitForTimeout(1500)` 是经验值，可能不够也可能浪费。

**方案**：
- **基于具体 API 的等待**：`waitForApi('POST /api/v2/bo/business_object')`
- **慢 API 警告**：> 1s 自动告警
- **网络重放**：录一次网络，回归测试时 mock 掉

```javascript
// e2e/helpers/network-waiter.js
export async function waitForApi(page, methodPath, options) {
  return page.waitForResponse(
    r => r.url().includes(methodPath) && r.request().method() === 'POST',
    options
  )
}
```

### 维度 6：测试套件分组 + 并行策略 —— **充分利用 CPU**

**问题**：当前 `workers: 1` 串行，25 个测试要 10+ 分钟。

**方案**：
- **按 project 分组**（smoke/features/permissions 已分）
- **workers 4-8 并行**（前提是 storageState + DB 隔离做好）
- **冒烟测试优先失败**（快速反馈）

## 实施优先级

| 维度 | 收益 | 工作量 | 优先级 |
|------|------|--------|--------|
| POM 封装高频页 | 代码 -50% | 中 | 🔴 P0 |
| 测试隔离 + 清理 | 解决脏数据 | 小 | 🔴 P0 |
| 自动截图 + Trace | 排查 -70% | 小 | 🟡 P1 |
| 菜单驱动导航 | 改 URL 不用 25 文件 | 中 | 🟡 P1 |
| API 智能等待 | 时间 -30% | 中 | 🟢 P2 |
| 并行化 | 时间 -50% | 高（需 DB 隔离） | 🟢 P2 |

## 已完成基础
- ✅ `global.setup.js` — 一次登录，全局共享 storageState
- ✅ `data-finder.js` — 智能查找或创建测试数据
- ✅ `auto-fixtures.js` — `navigateTo()` + `dataFinder` fixtures
- ✅ `playwright.config.js` — setup project + 三层 project

## 本次新增（本轮）
- ➕ `e2e/page-objects/ArchDataPage.js` — 架构数据管理页 POM
- ➕ `e2e/page-objects/GenericListPage.js` — 通用列表页 POM
- ➕ `e2e/page-objects/DetailDrawerPage.js` — 详情抽屉 POM
- ➕ `e2e/helpers/test-isolation.js` — 测试隔离 + 自动清理
- ➕ `e2e/helpers/auto-trace.js` — 自动 step 截图
- ➕ `e2e/helpers/network-waiter.js` — API 智能等待
- ➕ `e2e/helpers/menu-navigator.js` — 菜单驱动导航
- ➕ `e2e/demo/pom-migration-demo.spec.js` — 迁移前后对比 demo
