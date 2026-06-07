---
name: e2e-testing
description: Playwright E2E测试工作流。包含终端管理、Playwright规则、测试模板、运行与验证流程。当智能体需要编写或运行Playwright E2E测试时调用。
---

# Playwright E2E 测试工作流

> **浏览器工具规范：** `.trae/rules/SESSION_REMINDER.md` — 场景 A（自动化测试）禁止 MCP 工具，场景 B（开发调试）允许
> 认证单一事实源：`.trae/rules/frontend-test-auth.md`

## 一、终端管理铁律（5 个终端限制）

```
终端#1: npm run dev       (前端3004) → 永久占用，禁止运行其他命令
终端#2: python dev.py     (后端3010) → 永久占用，禁止运行其他命令
终端#3: npx playwright... (测试执行)  → 使用 target_terminal='new'
终端#4: show-report       (报告)      → 临时
终端#5: 备用
```

- **RunCommand 始终指定 `target_terminal`**（'new' 或已知空闲终端）
- **绝不在终端#1/#2 中运行测试命令**（会杀掉 dev server）

## 二、致命规则（违反会导致测试无效）

| # | 规则 | 后果 | 正确做法 |
|---|------|------|---------|
| 0 | **E2E 测试场景禁止使用 MCP 浏览器工具** | 多 Agent 并行冲突、Token 浪费、CDP 不稳定 | 只用 Playwright test runner 或 `test_helpers/browser_auth.py` |
| 1 | **禁止退回手动验证** | 测试用例被"手动验证"建议无限期搁置 | 页面结构复杂 → 渐进式适配（先基础选择器，再逐层深入） |
| 2 | 禁止 `waitForLoadState('networkidle')` | 永久卡死 | `domcontentloaded` + 元素等待 |
| 3 | 截图用 `testInfo.attach()` | 全截到首页 | 不用 `screenshot: 'on'` |
| 4 | 导航用 `navigateAndWaitForPage()` | 空白页/not_logged_in | `await navigateAndWaitForPage(page, url, opts)` |
| 5 | 权限用 `setAdminPermissions()` | 路由守卫拦截 | 同时改 localStorage + Pinia Store |
| 6 | 每个 project 指定 `testDir` | 扫描旧文件 | `testDir: './e2e/smoke'` |
| 7 | 测试终端与 dev server 分离 | 全部 ERR_CONNECTION_REFUSED | 3 个独立终端 |
| 8 | Element Plus 下拉用 `:visible` | 匹配隐藏 DOM | `.el-select-dropdown:visible` |
| 9 | API 请求带 `Authorization` | 返回 401 | 用 `getAuthHeaders(page)` |
| 10 | Python 脚本用 `browser_auth.py` | SPA 竞态 not_logged_in | `authenticated_page(target_url=...)` |

## 三、运行命令

```bash
# 环境预检
node scripts/e2e-precheck.js

# 冒烟测试
npx playwright test --project=smoke --reporter=line,html

# 功能测试
npx playwright test --project=features --reporter=line,html

# 查看报告（必须用 playwright 内置服务器）
npx playwright show-report --port 9326
```

## 四、运行后验证（三步法，必须执行）

1. **统计基线** — 检查 `playwright-report/data/` 下所有 .png 非 0KB
2. **HTTP 检查** — 报告页面执行脚本验证截图 URL 返回 200
3. **肉眼抽查** — 至少抽查 3 个测试截图（列表/详情/表单各一）

确认没有测试卡死/超时，确认 dev server 未被意外杀掉。

## 五、测试文件模板（Playwright Test Runner）

```javascript
/**
 * SXX: 场景名称
 * 规则: .trae/rules/e2e-testing.md
 */
import { test, expect } from '@playwright/test'
import { login, navigateAndWaitForPage, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('SXX: 场景名称', () => {
  test('C01: 测试用例', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/target-page', { expectedPath: 'target', waitForTable: true })
    await attachAndVerifyScreenshot(page, testInfo, '01-step-name', { expectedPath: 'target' })
  })
})
```

## 六、Python 脚本模板（单次验证/调试）

```python
from test_helpers.browser_auth import authenticated_page

async with authenticated_page(target_url='/system/archdata') as page:
    await page.wait_for_load_state('networkidle')
    await page.screenshot(path='test_result.png')
```

## 七、复杂页面结构应对指南

> **核心原则：测试复杂度 ≠ 不测试。页面结构越复杂，越需要自动化来保证一致性。**

### 标签页结构

```javascript
// [X] 错误：建议手动验证
test('标签页中的功能', async ({ page }) => {
  // "页面有标签页太复杂了，建议手动验证"
})

// [OK] 正确：先切换到目标标签，再操作
test('用户组管理标签 - 过滤图标', async ({ page }) => {
  await page.goto('/user-permission')
  // 先切换到"用户组管理"标签
  await page.getByRole('tab', { name: '用户组管理' }).click()
  // 然后验证表格内容
  await expect(page.locator('.el-table')).toBeVisible()
})
```

### 渐进式选择器策略

1. **先找最近的可信锚点**：`getByRole('tab', { name: '用户组管理' })`
2. **再定位目标元素**：在锚点的范围内查找
3. **不可靠的选择器 → 换思路**：不要硬编码 CSS 类名，用语义化定位

---

## 八、常见踩坑

| 问题 | 根因 | 解决 |
|------|------|------|
| 全部 ERR_CONNECTION_REFUSED | 服务未启动/被杀 | 预检脚本 + 终端分离 |
| 测试永久卡死 | networkidle 在 SPA 永不完成 | domcontentloaded + 元素等待 |
| 截图都是首页 | screenshot:'on' 在测试结束截图 | testInfo.attach() 手动截图 |
| 权限不生效 | 只改 localStorage 没改 Pinia | setAdminPermissions() |
| 报告图片无法显示 | python http.server | npx playwright show-report |
| 修复后测试被 skip | retry 缓存 | --retries=0 或删除 test-results/ |
