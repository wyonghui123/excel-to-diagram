# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: audit-log-management.spec.js >> 审计日志管理页面 (MetaListPage 集成) >> 1. 页面结构验证 - MetaListPage 集成
- Location: e2e\audit-log-management.spec.js:45:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.meta-list-page')
Expected: visible
Timeout: 30000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 30000ms
  - waiting for locator('.meta-list-page')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e5]:
    - generic [ref=e6]:
      - img [ref=e8]
      - heading "BIP应用架构管理" [level=2] [ref=e15]
      - paragraph [ref=e16]: 请登录以继续
    - generic [ref=e17]:
      - generic [ref=e18]:
        - generic [ref=e19]: 用户名
        - textbox "用户名" [ref=e20]:
          - /placeholder: 请输入用户名
      - generic [ref=e21]:
        - generic [ref=e22]: 密码
        - textbox "密码" [ref=e23]:
          - /placeholder: 请输入密码
      - button "登 录" [disabled] [ref=e24]:
        - generic [ref=e25]: 登 录
    - generic [ref=e26]: "默认管理员账号: admin / admin123"
  - generic [ref=e27]:
    - banner [ref=e28]:
      - generic [ref=e30] [cursor=pointer]:
        - img [ref=e31]
        - generic [ref=e38]: BIP应用架构管理
      - generic [ref=e39]:
        - button "AI 智能助手" [ref=e40] [cursor=pointer]:
          - generic:
            - img
        - button "收藏夹" [ref=e41] [cursor=pointer]:
          - generic:
            - img
        - button "最近访问" [ref=e42] [cursor=pointer]:
          - generic:
            - img
        - button [ref=e44] [cursor=pointer]:
          - generic:
            - img
        - button "U 用户" [ref=e47] [cursor=pointer]:
          - generic [ref=e48]: U
          - generic [ref=e49]: 用户
          - img [ref=e51]
    - button [ref=e55] [cursor=pointer]:
      - img [ref=e56]
    - generic [ref=e58]:
      - complementary:
        - navigation [ref=e59]:
          - generic [ref=e60] [cursor=pointer]:
            - generic: 首页
      - main [ref=e62]:
        - generic [ref=e63]:
          - main [ref=e64]:
            - generic [ref=e65]:
              - heading "快捷应用" [level=2] [ref=e67]
              - generic [ref=e69] [cursor=pointer]:
                - img [ref=e71]
                - generic [ref=e74]: 首页
            - generic [ref=e76]:
              - generic [ref=e77]:
                - generic [ref=e78]: 常用产品版本
                - generic [ref=e79]: 点击快速进入架构数据管理
              - generic [ref=e80]: 暂无常用产品版本，请先访问架构数据管理
            - generic [ref=e82]:
              - heading "统计概览" [level=3] [ref=e83]
              - generic [ref=e84]:
                - generic [ref=e85]: 平台全貌
                - generic [ref=e86]:
                  - generic [ref=e87]:
                    - img [ref=e89]
                    - generic [ref=e92]:
                      - generic [ref=e93]: "5"
                      - generic [ref=e94]: 产品
                    - generic [ref=e95]: "+2"
                  - generic [ref=e96]:
                    - img [ref=e98]
                    - generic [ref=e102]:
                      - generic [ref=e103]: "11"
                      - generic [ref=e104]: 版本
                    - generic [ref=e105]: "+7"
                  - generic [ref=e106]:
                    - img [ref=e108]
                    - generic [ref=e111]:
                      - generic [ref=e112]: "116"
                      - generic [ref=e113]: 领域
                    - generic [ref=e114]: "+97"
                  - generic [ref=e115]:
                    - img [ref=e117]
                    - generic [ref=e119]:
                      - generic [ref=e120]: "14298"
                      - generic [ref=e121]: 业务对象
                    - generic [ref=e122]: "+12249"
                  - generic [ref=e123]:
                    - img [ref=e125]
                    - generic [ref=e131]:
                      - generic [ref=e132]: "19306"
                      - generic [ref=e133]: 关系
                    - generic [ref=e134]: "+16550"
          - paragraph [ref=e136]: © 2026 BIP应用架构管理
```

# Test source

```ts
  1   | /**
  2   |  * 审计日志管理页面 E2E 测试
  3   |  * 
  4   |  * 测试范围：
  5   |  * 1. 页面结构验证（MetaListPage 集成）
  6   |  * 2. 表格数据加载
  7   |  * 3. Badge 标签渲染（log_category, log_level, action）
  8   |  * 4. 分页功能
  9   |  * 5. 搜索功能
  10  |  * 6. 排序功能
  11  |  * 7. 详情抽屉
  12  |  * 8. 工具栏操作
  13  |  */
  14  | 
  15  | import { test, expect } from '@playwright/test'
  16  | 
  17  | test.describe('审计日志管理页面 (MetaListPage 集成)', () => {
  18  |   
  19  |   test.beforeEach(async ({ page }) => {
  20  |     // 登录
  21  |     await page.goto('/')
  22  |     await page.waitForLoadState('networkidle')
  23  |     
  24  |     const usernameInput = page.locator('input[type="text"], input[placeholder*="用户名"], input[placeholder*="username"]')
  25  |     const passwordInput = page.locator('input[type="password"]')
  26  |     
  27  |     if (await usernameInput.isVisible()) {
  28  |       await usernameInput.fill('admin')
  29  |       await passwordInput.fill('admin123')
  30  |       
  31  |       const loginBtn = page.locator('button[type="submit"], .login-btn')
  32  |       if (await loginBtn.isVisible()) {
  33  |         await loginBtn.click()
  34  |       }
  35  |     }
  36  |     
  37  |     await page.waitForTimeout(2000)
  38  |     
  39  |     // 导航到系统管理页面
  40  |     await page.goto('/system-admin')
  41  |     await page.waitForLoadState('networkidle')
  42  |     await page.waitForTimeout(3000)
  43  |   })
  44  | 
  45  |   test('1. 页面结构验证 - MetaListPage 集成', async ({ page }) => {
  46  |     // 验证 MetaListPage 组件存在
  47  |     const metaListPage = page.locator('.meta-list-page')
> 48  |     await expect(metaListPage).toBeVisible()
      |                                ^ Error: expect(locator).toBeVisible() failed
  49  | 
  50  |     // 验证合并的 toolbar 存在
  51  |     const toolbar = page.locator('.toolbar')
  52  |     await expect(toolbar).toBeVisible()
  53  | 
  54  |     // 验证表格存在
  55  |     const table = page.locator('.el-table')
  56  |     await expect(table).toBeVisible()
  57  | 
  58  |     // 验证分页存在
  59  |     const pagination = page.locator('.el-pagination')
  60  |     await expect(pagination).toBeVisible()
  61  | 
  62  |     // 验证旧版 filter-bar 已移除
  63  |     const oldFilterBar = page.locator('.filter-bar')
  64  |     const filterBarCount = await oldFilterBar.count()
  65  |     expect(filterBarCount).toBe(0)
  66  |     
  67  |     console.log('页面结构验证通过')
  68  |   })
  69  | 
  70  |   test('2. 表格数据加载', async ({ page }) => {
  71  |     // 等待表格加载
  72  |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  73  |     await page.waitForTimeout(2000)
  74  | 
  75  |     // 验证有数据行
  76  |     const rows = page.locator('.el-table__body tr')
  77  |     const rowCount = await rows.count()
  78  |     expect(rowCount).toBeGreaterThan(0)
  79  |     console.log(`表格加载了 ${rowCount} 行数据`)
  80  | 
  81  |     // 验证表格列标题
  82  |     const headers = page.locator('.el-table__header th .cell')
  83  |     const headerCount = await headers.count()
  84  |     expect(headerCount).toBeGreaterThan(5)
  85  |     console.log(`表格有 ${headerCount} 列`)
  86  |   })
  87  | 
  88  |   test('3. Badge 标签渲染验证', async ({ page }) => {
  89  |     // 等待表格加载
  90  |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  91  |     await page.waitForTimeout(2000)
  92  | 
  93  |     // 验证日志类型 Badge
  94  |     const categoryBadges = page.locator('.el-table__body .el-tag')
  95  |     const badgeCount = await categoryBadges.count()
  96  |     expect(badgeCount).toBeGreaterThan(0)
  97  |     console.log(`发现 ${badgeCount} 个 Badge 标签`)
  98  | 
  99  |     // 验证第一个 Badge 的文本不是空的
  100 |     const firstBadge = categoryBadges.first()
  101 |     const badgeText = await firstBadge.textContent()
  102 |     expect(badgeText.trim().length).toBeGreaterThan(0)
  103 |     console.log(`Badge 文本: "${badgeText.trim()}"`
  104 |     )
  105 |   })
  106 | 
  107 |   test('4. 分页功能', async ({ page }) => {
  108 |     // 等待表格加载
  109 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  110 |     await page.waitForTimeout(2000)
  111 | 
  112 |     // 验证分页信息显示
  113 |     const paginationInfo = page.locator('.el-pagination__total')
  114 |     if (await paginationInfo.isVisible()) {
  115 |       const text = await paginationInfo.textContent()
  116 |       console.log(`分页信息: ${text}`)
  117 |     }
  118 | 
  119 |     // 验证每页条数选择器
  120 |     const pageSizeSelect = page.locator('.el-pagination__sizes .el-input__inner')
  121 |     if (await pageSizeSelect.isVisible()) {
  122 |       const pageSize = await pageSizeSelect.inputValue()
  123 |       console.log(`当前每页条数: ${pageSize}`)
  124 |     }
  125 | 
  126 |     // 验证页码
  127 |     const currentPage = page.locator('.el-pagination__jump input')
  128 |     if (await currentPage.isVisible()) {
  129 |       const pageNum = await currentPage.inputValue()
  130 |       console.log(`当前页码: ${pageNum}`)
  131 |     }
  132 |   })
  133 | 
  134 |   test('5. 搜索功能', async ({ page }) => {
  135 |     // 等待表格加载
  136 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  137 |     await page.waitForTimeout(2000)
  138 | 
  139 |     // 查找搜索输入框
  140 |     const searchInput = page.locator('.toolbar .el-input input')
  141 |     if (await searchInput.isVisible()) {
  142 |       // 输入搜索关键词
  143 |       await searchInput.fill('admin')
  144 |       await page.waitForTimeout(500)
  145 | 
  146 |       // 点击搜索按钮
  147 |       const searchBtn = page.locator('.toolbar button:has-text("搜索")')
  148 |       if (await searchBtn.isVisible()) {
```