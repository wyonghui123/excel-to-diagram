# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: audit-log-management.spec.js >> 审计日志管理页面 (MetaListPage 集成) >> 8. 工具栏导出按钮
- Location: e2e\audit-log-management.spec.js:222:3

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
  174 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
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
> 224 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
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
  275 |       for (const el of elements) {
  276 |         const style = window.getComputedStyle(el)
  277 |         if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && 
  278 |             el.scrollHeight > el.clientHeight) {
  279 |           scrollCount++
  280 |           scrollElements.push({
  281 |             class: el.className.substring(0, 50),
  282 |             height: el.clientHeight,
  283 |             scrollHeight: el.scrollHeight
  284 |           })
  285 |         }
  286 |       }
  287 |       
  288 |       return { count: scrollCount, elements: scrollElements.slice(0, 5) }
  289 |     })
  290 | 
  291 |     console.log(`可滚动元素数量: ${scrollInfo.count}`)
  292 |     if (scrollInfo.count === 1) {
  293 |       console.log('只有1个滚动容器，符合单一滚动源原则')
  294 |     }
  295 |   })
  296 | })
  297 | 
  298 | test.describe('审计日志 API 集成测试', () => {
  299 |   
  300 |   test('后端 API 返回正确的数据结构', async ({ request }) => {
  301 |     // 登录获取 token
  302 |     const loginResponse = await request.post('/api/v1/auth/login', {
  303 |       data: {
  304 |         username: 'admin',
  305 |         password: 'admin123'
  306 |       }
  307 |     })
  308 |     
  309 |     expect(loginResponse.ok()).toBeTruthy()
  310 |     const loginData = await loginResponse.json()
  311 |     expect(loginData.success).toBe(true)
  312 |     
  313 |     const token = loginData.data?.token
  314 |     expect(token).toBeTruthy()
  315 | 
  316 |     // 调用审计日志 API
  317 |     const auditResponse = await request.get('/api/v2/bo/audit_log', {
  318 |       headers: {
  319 |         Authorization: `Bearer ${token}`
  320 |       },
  321 |       params: {
  322 |         page: 1,
  323 |         page_size: 10
  324 |       }
```