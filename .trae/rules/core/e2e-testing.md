# E2E 测试规范（精简索引）

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 621-1081 行）
> **完整 E2E 规范见 `e2e-simplification.md`（已存在）**

## 核心经验教训

### 1. API 响应格式：分页数据不是数组

[CRITICAL] 所有 V2 BO API 返回分页格式，不是直接数组！

```javascript
// [X] 错误：假设 data.data 是数组
const items = data.data || data

// [OK] 正确：解析分页格式
const items = data.data?.items || data.data?.records || data.data?.list || data.data?.rows || (Array.isArray(data.data) ? data.data : [])
```

### 2. Token 认证：必须从 localStorage 获取 auth_token

[CRITICAL] `page.request` 不共享浏览器认证状态！

```javascript
// [X] 错误：page.request 不带 token，返回 401
const resp = await page.request.get('/api/v2/bo/product')

// [OK] 正确：从 localStorage 获取 token，显式传递
const token = await page.evaluate(() => localStorage.getItem('auth_token'))
const resp = await page.request.get('/api/v2/bo/product', {
  headers: { 'Authorization': `Bearer ${token}` }
})
```

### 3. Element Plus 下拉选择器：必须使用 :visible 约束

```javascript
// [OK] 正确：只匹配可见的下拉选项
const options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
```

### 4. 架构数据页面：需要先选择产品和版本

```javascript
// [OK] 正确：通过 URL 参数直接选择产品和版本
await page.goto(`/system/archdata?productId=${productId}&versionId=${versionId}&tab=business_object`)
```

### 5. 登录遮罩层：必须等待 .login-overlay 消失

```javascript
async function login(page) {
  await page.goto('/')
  await page.fill('input[type="text"], input[name="username"]', 'admin')
  await page.fill('input[type="password"]', 'admin123')
  await page.click('button[type="submit"]')

  // [CRITICAL] 等待登录遮罩层消失
  const overlay = page.locator('.login-overlay')
  try {
    await overlay.waitFor({ state: 'hidden', timeout: 10000 })
  } catch (e) {
    // 遮罩层可能已经不存在
  }
}
```

## Playwright 关键经验

### 10. [CRITICAL] 禁止使用 waitForLoadState('networkidle')

Vue SPA 应用中 networkidle 会导致测试永久卡死（心跳、轮询等持续请求）。

```javascript
// [OK] 正确
await page.waitForLoadState('domcontentloaded')
await page.locator('.el-table').first().waitFor({ state: 'visible', timeout: 15000 })
```

### 11. [CRITICAL] 截图必须使用 testInfo.attach() 嵌入报告

```javascript
const screenshot = await page.screenshot({ fullPage: true })
await testInfo.attach('产品管理页面', {
  body: screenshot,
  contentType: 'image/png'
})
```

### 12. [CRITICAL] 页面导航必须使用 navigateAndWaitForPage()

```javascript
// [OK] 正确
await navigateAndWaitForPage(page, '/product-management', { waitForTable: true })
```

### 17. [CRITICAL] 运行 E2E 测试前必须验证环境

```bash
# 步骤1: 确认前端服务（终端 A）
curl http://localhost:3004/
# 步骤2: 确认后端服务（终端 B）
curl http://localhost:3010/api/v1/health
# 步骤3: 在第三个终端运行测试（终端 C）
npx playwright test --project=smoke --reporter=line,html
```

## E2E 测试文件索引

| 目录 | 文件 | 场景 | 优先级 |
|------|------|------|--------|
| e2e/smoke/ | auth.smoke.spec.js | S01: 认证与账户设置 | P0 |
| e2e/smoke/ | arch-data.smoke.spec.js | S02: 架构数据页面 | P0 |
| e2e/features/ | arch-data-crud.spec.js | S03: 业务对象/关系 CRUD | P1 |
| e2e/features/ | arch-data-filter-scope.spec.js | S04: 过滤与范围选择 | P1 |
| e2e/features/ | import-export.spec.js | S05: 导入导出 | P1 |
| e2e/features/ | user-role.spec.js | S06: 用户角色管理 | P1 |
| e2e/features/ | permission.spec.js | S07: 权限管理 | P1 |
| e2e/features/ | enum-management.spec.js | S08: 枚举管理 | P1 |
| e2e/features/ | audit-log.spec.js | S09: 审计日志 | P2 |
| e2e/features/ | diagram.spec.js | S10: 架构图 | P2 |
| e2e/features/ | product-version.spec.js | S11: 产品版本管理 | P1 |

**完整规范**：[../e2e-simplification.md](../e2e-simplification.md)（v2 简化方案）

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分（提取核心经验，详细见 e2e-simplification.md） |
