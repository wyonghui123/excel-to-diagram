# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: audit-log-management.spec.js >> 审计日志管理页面 (MetaListPage 集成) >> 7. 详情抽屉
- Location: e2e\audit-log-management.spec.js:172:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.el-table__body tr') to be visible

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
  149 |         await searchBtn.click()
  150 |         await page.waitForTimeout(2000)
  151 |         console.log('搜索功能正常')
  152 |       }
  153 |     }
  154 |   })
  155 | 
  156 |   test('6. 排序功能', async ({ page }) => {
  157 |     // 等待表格加载
  158 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  159 |     await page.waitForTimeout(2000)
  160 | 
  161 |     // 悬停到第一列表头
  162 |     const firstHeader = page.locator('.el-table__header th').first()
  163 |     await firstHeader.hover()
  164 |     await page.waitForTimeout(500)
  165 | 
  166 |     // 点击第一列表头的排序
  167 |     await firstHeader.click()
  168 |     await page.waitForTimeout(1000)
  169 |     console.log('排序功能正常')
  170 |   })
  171 | 
  172 |   test('7. 详情抽屉', async ({ page }) => {
  173 |     // 等待表格加载
> 174 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  175 |     await page.waitForTimeout(2000)
  176 | 
  177 |     // 点击第一行（MetaListPage 点击行触发 detail 事件）
  178 |     const firstRow = page.locator('.el-table__body tr').first()
  179 |     await firstRow.click()
  180 |     await page.waitForTimeout(2000)
  181 | 
  182 |     // 验证抽屉打开 — 使用 .first() 因为可能有多个 drawer
  183 |     const drawer = page.locator('.el-drawer').first()
  184 |     if (await drawer.isVisible()) {
  185 |       // 验证抽屉标题
  186 |       const drawerTitle = drawer.locator('.el-drawer__header span')
  187 |       const titleText = await drawerTitle.textContent()
  188 |       console.log(`抽屉标题: "${titleText}"`)
  189 |       expect(titleText).toContain('审计日志')
  190 | 
  191 |       // 验证抽屉内容
  192 |       const descriptions = drawer.locator('.el-descriptions')
  193 |       if (await descriptions.isVisible()) {
  194 |         console.log('详情内容 (el-descriptions) 已显示')
  195 |       }
  196 | 
  197 |       // 关闭抽屉
  198 |       const closeBtn = drawer.locator('.el-drawer__close')
  199 |       if (await closeBtn.isVisible()) {
  200 |         await closeBtn.click()
  201 |         await page.waitForTimeout(500)
  202 |       }
  203 |       console.log('详情抽屉功能正常')
  204 |     } else {
  205 |       console.log('详情抽屉未打开，可能需要点击详情按钮')
  206 |       // 尝试点击详情按钮
  207 |       const detailBtn = page.locator('.el-table__body .el-button:has-text("详情")').first()
  208 |       if (await detailBtn.isVisible()) {
  209 |         await detailBtn.click()
  210 |         await page.waitForTimeout(2000)
  211 |         if (await drawer.isVisible()) {
  212 |           console.log('详情抽屉功能正常 (点击详情按钮后)')
  213 |           const closeBtn = drawer.locator('.el-drawer__close')
  214 |           if (await closeBtn.isVisible()) {
  215 |             await closeBtn.click()
  216 |           }
  217 |         }
  218 |       }
  219 |     }
  220 |   })
  221 | 
  222 |   test('8. 工具栏导出按钮', async ({ page }) => {
  223 |     // 等待表格加载
  224 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  225 |     await page.waitForTimeout(2000)
  226 | 
  227 |     // 查找导出按钮
  228 |     const exportBtn = page.locator('.toolbar button:has-text("导出")')
  229 |     
  230 |     if (await exportBtn.isVisible()) {
  231 |       console.log('导出按钮存在')
  232 |       
  233 |       // 点击导出按钮
  234 |       await exportBtn.click()
  235 |       await page.waitForTimeout(1500)
  236 | 
  237 |       // 验证导出对话框出现
  238 |       const exportDialog = page.locator('.el-dialog')
  239 |       if (await exportDialog.isVisible()) {
  240 |         console.log('导出对话框正常打开')
  241 | 
  242 |         // 关闭对话框
  243 |         const cancelBtn = page.locator('.el-dialog button:has-text("取消")')
  244 |         if (await cancelBtn.isVisible()) {
  245 |           await cancelBtn.click()
  246 |         }
  247 |       }
  248 |     } else {
  249 |       console.log('导出按钮未找到')
  250 |     }
  251 |   })
  252 | 
  253 |   test('9. 滚动条行为验证 - 单一滚动源原则', async ({ page }) => {
  254 |     // 等待表格加载
  255 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  256 |     await page.waitForTimeout(2000)
  257 | 
  258 |     // 获取视口信息
  259 |     const viewport = page.viewportSize()
  260 |     console.log(`视口大小: ${viewport.width}x${viewport.height}`)
  261 | 
  262 |     // 检查 table-section
  263 |     const tableSection = page.locator('.table-section')
  264 |     if (await tableSection.isVisible()) {
  265 |       const box = await tableSection.boundingBox()
  266 |       console.log(`表格区域高度: ${box?.height}px`)
  267 |     }
  268 | 
  269 |     // 验证只有 el-scrollbar__wrap 有垂直滚动
  270 |     const scrollInfo = await page.evaluate(() => {
  271 |       const elements = document.querySelectorAll('*')
  272 |       let scrollCount = 0
  273 |       let scrollElements = []
  274 |       
```