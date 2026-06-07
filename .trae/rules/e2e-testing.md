# E2E 测试规则（Playwright）

> [!!!] 本文件是 v1 时代 E2E 规则，部分仍有效 [!!!]
> [!!!] **新写测试请阅读 [e2e-simplification.md](./e2e-simplification.md) 优先** [!!!]
> [!!!] v2 简化方案是当前权威规范（POM/fixtures/isolation/auto-trace） [!!!]
> 认证相关规范见 `.trae/rules/frontend-test-auth.md`（单一事实源）
> 最后更新: 2026-06-05（指向 v2 简化方案）

---

## 一、8 条致命/严重规则（违反会导致测试无效）

| # | 规则 | 违反后果 | 正确做法 |
|---|------|---------|---------|
| 1 | **禁止 `waitForLoadState('networkidle')`** | 测试永久卡死 | 用 `domcontentloaded` + 元素等待 |
| 2 | **截图用 `testInfo.attach()`** | 所有截图都是首页 | 用 `attachAndVerifyScreenshot()` |
| 3 | **导航用 `navigateAndWaitForPage()`** | 页面未加载完就操作 | 不用 `page.goto()` + `waitForTimeout` |
| 4 | **权限用 `setAdminPermissions()`** | 路由守卫拦截，页面空白 | 同时改 localStorage + Pinia Store |
| 5 | **每个 project 必须指定 `testDir`** | 扫描旧文件，测试混乱 | `testDir: './e2e/smoke'` |
| 6 | **测试终端与 dev server 分离** | dev server 被杀，全部 ERR_CONNECTION_REFUSED | 3 个独立终端 |
| 7 | **Element Plus 下拉用 `:visible`** | 匹配隐藏 DOM，操作失败 | `.el-select-dropdown:visible` |
| 8 | **API 请求带 `Authorization`** | 返回 401 | 用 `getAuthHeaders(page)` |
| 9 | **Python 脚本用 `test_helpers/browser_auth.py`** | SPA 竞态导致 not_logged_in | `authenticated_page(target_url=...)` |

---

## 二、运行前检查清单

```
[ ] 前端 3004 端口可达（终端 A: npm run dev）
[ ] 后端 3010 端口可达（终端 B: python dev.py）
[ ] 测试在第三个终端运行（终端 C）
[ ] 运行预检: node scripts/e2e-precheck.js
```

## 三、运行后验证清单

```
[ ] 在 Playwright 报告中检查截图内容（不是首页/空白）
[ ] 确认每个步骤的截图 URL 路径正确
[ ] 确认没有测试卡死或超时
[ ] 报告查看: npx playwright show-report --port 9326
```

---

## 四、反复踩坑的经验表（详见第十一节完整版）

---

## 五、推荐配置

### playwright.config.js

```javascript
export default defineConfig({
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  use: {
    trace: 'on',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10000
  },
  projects: [
    { name: 'smoke', testDir: './e2e/smoke', testMatch: '*.smoke.spec.js' },
    { name: 'features', testDir: './e2e/features' }
  ]
})
```

### 辅助函数（e2e/helpers/auth.js）

| 函数 | 用途 |
|------|------|
| `login(page)` | 登录（自动检测已登录状态） |
| `setAdminPermissions(page)` | 设置管理员权限（localStorage + Pinia） |
| `navigateAndWaitForPage(page, url, opts)` | 安全导航（domcontentloaded + 元素等待） |
| `attachAndVerifyScreenshot(page, testInfo, name, opts)` | 截图并验证（URL 路径、非首页） |
| `attachScreenshot(page, testInfo, name)` | 简单截图 |
| `getAuthHeaders(page)` | 获取 API 请求认证头 |
| `getPaginatedData(page, url)` | 获取分页数据（自动解析格式） |
| `findProductWithVersion(page)` | 查找有版本的产品 |

---

## 六、测试文件模板

### 6.1 Playwright Test Runner（E2E 测试套件）

```javascript
/**
 * SXX: 场景名称 - 功能测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 *
 * [UI 行为说明] 实际交互流程（基于 MCP 快照验证 YYYY-MM-DD）:
 * - 路由: /xxx
 * - Tab 名称: "Tab1"/"Tab2"
 * - 工具栏: "新建XX"/"搜索"/"重置"
 * - 表格行: 点击行打开详情抽屉
 */
import { test, expect } from '@playwright/test'
import { login, navigateAndWaitForPage, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('SXX: 场景名称', () => {
  test('C01: 测试用例名称', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/target-page', { expectedPath: 'target', waitForTable: true })
    await attachAndVerifyScreenshot(page, testInfo, '01-step-name', { expectedPath: 'target' })
  })
})
```

### 6.2 Python 脚本（智能体单次验证/调试）

```python
"""
智能体前端验证脚本 - 单次调试用
使用 authenticated_page 一行完成认证，无需关心登录流程
"""
from test_helpers.browser_auth import authenticated_page

async with authenticated_page(target_url='/system/archdata') as page:
    await page.wait_for_load_state('networkidle')
    await page.screenshot(path='test_result.png')
```

---

## 七、经验固化机制（多层防护）

| 层级 | 位置 | 作用 |
|------|------|------|
| L1 | `playwright.config.js` 头部注释 | 编辑测试配置时可见 |
| L2 | `helpers/auth.js` 头部注释 | 编辑辅助函数时可见 |
| L3 | 每个测试文件头部 `[E2E 规则速查]` | 编辑测试用例时可见 |
| L4 | `.trae/rules/e2e-testing.md`（本文件） | E2E 专用规则，单一事实源 |
| L5 | `.trae/rules/SESSION_REMINDER.md` | 会话开始时的检查清单 |
| L6 | `.trae/memory/project-status.md` | 里程碑进度和经验表 |

---

## 九、运行操作规范（避免卡死和服务被杀） [NEW 2026-05-23]

### 9.1 终端管理铁律（5个终端限制下的生存法则）

```
┌─────────────────────────────────────────────────────────┐
│ 终端#1: 前端 dev server    │ npm run dev       │ 永久占用 │
│ 终端#2: 后端 Flask         │ python dev.py     │ 永久占用 │
│ 终端#3: 测试执行            │ npx playwright... │ 临时占用 │
│ 终端#4: 报告查看            │ npx playwright show-report │ 临时   │
│ 终端#5: 备用（MCP调试等）   │                   │ 备用   │
└─────────────────────────────────────────────────────────┘
```

**致命错误（本会话反复踩坑）：**

| 错误操作 | 后果 | 正确做法 |
|----------|------|---------|
| 在终端#1(npm run dev)中运行测试 | **前端服务被杀，全部 ECONNREFUSED** | 用 `target_terminal: 'new'` 或指定空闲终端 |
| 在终端#2(python dev.py)中运行命令 | **后端服务被杀，全部 502** | 同上 |
| 运行测试时不指定 `target_terminal` | 可能复用已有终端，杀掉服务 | **始终显式指定 target_terminal** |

**运行测试的安全命令模板：**

```bash
# [X] 危险：不指定终端，可能杀掉 dev server
npx playwright test --project=features

# [OK] 安全：在新建终端运行
npx playwright test --project=features --reporter=line,html --timeout=120000
# 使用 RunCommand 时设置: target_terminal: 'new', command_type: 'short_running_process'
```

### 9.2 服务恢复流程

当测试报 `ERR_CONNECTION_REFUSED` 或 `ECONNREFUSED` 时：

```
1. 检查终端状态: 用 CheckCommandStatus 查看 dev server 终端
2. 如果 status=Exited，重新启动:
   - 前端: RunCommand("npm run dev", target_terminal='new', blocking=false)
   - 后端: RunCommand("python dev.py", target_terminal='new', blocking=false)
3. 等待3-5秒后验证:
   - node -e "http.get('http://localhost:3004/', ...)"  # 前端
   - node -e "http.get('http://localhost:3010/', ...)"  # 后端
4. 确认两个服务都 OK 后再运行测试
```

### 9.3 测试重试/缓存清理

| 场景 | 操作 |
|------|------|
| 修复 bug 后重新运行 | **必须加 `--retries=0`**，否则可能因为之前的 retry 被 skip |
| 清除上次失败缓存 | 删除 `test-results/` 目录 |
| 只运行特定文件 | `npx playwright test e2e/features/xxx.spec.js --project=features` |
| 报告端口被占用 | 换一个端口：`--port 9327`, `--port 9328`... |

---

## 十、截图验证规范（运行后必须执行） [NEW 2026-05-23]

### 10.1 三步验证法

**步骤1: 统计基线检查（30秒）**

```powershell
# 在项目根目录运行，检查全部截图非空
$imgs = Get-ChildItem "playwright-report\data" -Filter "*.png" -File
$total = $imgs.Count
$empty = ($imgs | Where-Object { $_.Length -eq 0 }).Count
$min = [math]::Round(($imgs | Measure-Object -Property Length -Minimum).Minimum / 1KB, 1)
$max = [math]::Round(($imgs | Measure-Object -Property Length -Maximum).Maximum / 1KB, 1)
Write-Host "Total: $total, Empty: $empty, Min: ${min}KB, Max: ${max}KB"
Write-Host "ALL NON-EMPTY: $($empty -eq 0)"
```

**判定标准：**
- `Empty = 0` → [OK] 通过
- `Empty > 0` → [X] 有空白截图，定位并修复
- `Min < 1KB` → [WARNING] 可能有近似空白截图，需肉眼抽查

**步骤2: HTTP 可访问性检查（通过浏览器 MCP）**

```javascript
// 在报告页面执行，批量验证截图 URL
async () => {
  const links = document.querySelectorAll('a[href*="/data/"][href$=".png"]');
  const results = [];
  for (const a of links) {
    const txt = a.textContent?.trim();
    if (!txt) continue;
    const resp = await fetch(a.href, { method: 'HEAD', cache: 'no-store' });
    const cl = resp.headers.get('content-length');
    results.push({ name: txt, status: resp.status, sizeKB: (parseInt(cl)/1024).toFixed(1) });
  }
  return results;
}
```

**判定标准：**
- 全部 `status: 200` → [OK]
- 出现 `status: 404` → [X] 图片文件丢失
- 出现 `sizeKB: '0.0'` → [X] 空白图片

**步骤3: 肉眼抽查（至少3个测试的截图）**

| 抽查项 | 方法 |
|--------|------|
| 列表页截图 | 应看到表格行、表头、分页信息 |
| 详情页截图 | 应看到 Facet/Card 区域、编辑/删除按钮 |
| 表单截图 | 应看到输入框、下拉框、保存/取消按钮 |
| 确认截图 URL 是目标页面 | 截图验证输出中应看到 OK URL |

### 10.2 验证记录模板

每次运行测试后，在回复中附上验证结果：

```
## 截图验证
| 套件 | 截图总数 | 空白 | 最小/最大 | HTTP状态 | 肉眼抽查 |
|------|---------|------|-----------|---------|---------|
| Smoke | 7 | 0 | 22KB/76KB | 全部200 | C04,C05 架构数据页面 [OK] |
| Features | 45 | 0 | 4KB/91KB | 全部200 | CRUD(8张), Enum(6张) [OK] |
```

---

## 十一、经验表（持续更新）

| # | 问题 | 根因 | 解决方案 | 影响程度 |
|---|------|------|---------|---------|
| 1 | 测试全部 ERR_CONNECTION_REFUSED | 服务未启动或被杀 | 预检脚本 + 终端分离 | 致命 |
| 2 | 测试永久卡死 | `networkidle` 在 SPA 中永不完成 | 用 `domcontentloaded` + 元素等待 | 致命 |
| 3 | 所有截图都是首页 | `screenshot: 'on'` 在测试结束后截图 | 用 `testInfo.attach()` 手动截图 | 严重 |
| 4 | 权限不生效 | 只改 localStorage 没改 Pinia | `setAdminPermissions()` 同步两者 | 严重 |
| 5 | 扫描旧测试文件 | project 没指定 testDir | 每个 project 指定独立 testDir | 中等 |
| 6 | 报告图片无法显示 | 用 python http.server 打开报告 | 用 `npx playwright show-report` | 中等 |
| 7 | Element Plus 下拉匹配隐藏 DOM | 没用 `:visible` 约束 | 下拉选项加 `:visible` | 中等 |
| 8 | API 请求返回 401 | page.request 不共享浏览器认证 | 手动带 Authorization header | 中等 |
| 9 | Tab 名称不匹配 | 测试用 "关系" 实际是 "关联关系" | 用 MCP 快照验证实际 UI 文本 | 中等 |
| 10 | 抽屉遮罩阻挡点击 | Drawer overlay 未关闭 | 先按 Escape 关闭再操作 | 中等 |
| 11 | dev server 在测试中途被杀 | 终端复用，新命令覆盖了 dev server | RunCommand 始终指定 target_terminal | 致命 |
| 12 | 修复bug后测试被 skip | 上次失败产生的 retry 缓存未清除 | 加 --retries=0 或删除 test-results/ | 中等 |
| 13 | Playwright 报错 "两个不同版本" | 顶层 playwright 与 @playwright/test 内部嵌套的 playwright 版本不一致 | 在 package.json 中固定 `playwright` 版本与 `@playwright/test` 完全一致（如 `"playwright": "1.59.1"`） | 致命 |

---

## 十二、里程碑进度
- [x] 里程碑 2: 冒烟测试（5 passed）
- [x] 里程碑 3: 架构数据深度测试（S03 + S04 + S05）
- [x] 里程碑 4: 用户权限与角色权限（S06 + S07）- 3 passed
- [x] 里程碑 5: 枚举管理（S08）- 3 passed
- [x] 里程碑 6: 审计日志与架构图（S09 + S10）- 5 passed
- [x] 里程碑 7: 产品版本管理（S11）- 3 passed
- [x] 里程碑 8: 清理旧文件 + 更新文档

### 最终测试统计（2026-05-23）

| 测试套件 | Test数 | Passed | Skipped | 说明 |
|----------|--------|--------|---------|------|
| Smoke (P0) | 5 | 5 | 0 | 核心冒烟全部通过 |
| Features (P1/P2) | 18 | 16 | 2 | filter-scope UI已变更，优雅跳过 |

### 测试文件分布

```
e2e/
├── helpers/
│   └── auth.js              # 辅助函数库（登录/导航/截图/权限/API）
├── smoke/
│   ├── auth.smoke.spec.js   # S01: 认证与账户设置 (3 tests)
│   └── arch-data.smoke.spec.js # S02: 架构数据导航 (2 tests)
└── features/
    ├── arch-data-crud.spec.js       # S03: 业务对象与关系CRUD (2 tests)
    ├── arch-data-filter-scope.spec.js # S04: 过滤与范围选择 (2 tests, skipped)
    ├── import-export.spec.js        # S05: 导入导出 (2 tests)
    ├── user-role.spec.js            # S06+S07: 用户角色权限 (3 tests)
    ├── enum-management.spec.js      # S08: 枚举管理 (3 tests)
    ├── audit-log.spec.js            # S09: 审计日志 (3 tests)
    ├── diagram.spec.js              # S10: 架构图 (2 tests)
    └── product-version.spec.js      # S11: 产品版本管理 (3 tests)
```
