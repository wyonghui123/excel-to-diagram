# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: annotation-metadata.spec.js >> Annotation UI Tests - Annotation UI 测试 >> TC-ANN-UI-001: 服务模块详情页应显示备注面板
- Location: e2e\annotation-metadata.spec.js:290:3

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
      - main [ref=e62]
```

# Test source

```ts
  197 |       },
  198 |       data: {
  199 |         target_type: 'business_object',
  200 |         target_id: 1,
  201 |         category: 'info',
  202 |         content: 'E2E测试 - 业务对象备注'
  203 |       }
  204 |     })
  205 | 
  206 |     expect(createResponse.ok()).toBeTruthy()
  207 |     const createData = await createResponse.json()
  208 |     expect(createData.success).toBe(true)
  209 |     const annotationId = createData.data.id
  210 | 
  211 |     console.log(`✅ 创建 business_object annotation: ID=${annotationId}`)
  212 | 
  213 |     // 按目标查询
  214 |     const listResponse = await request.get(
  215 |       `${BASE_URL}/api/v1/annotations/by-target?target_type=business_object&target_id=1`,
  216 |       { headers: { Authorization: `Bearer ${token}` } }
  217 |     )
  218 | 
  219 |     expect(listResponse.ok()).toBeTruthy()
  220 |     const listData = await listResponse.json()
  221 |     expect(listData.success).toBe(true)
  222 |     expect(listData.data.length).toBeGreaterThanOrEqual(1)
  223 | 
  224 |     console.log(`✅ 查询 business_object annotations: ${listData.data.length} 条`)
  225 | 
  226 |     // 清理
  227 |     await request.delete(`${BASE_URL}/api/v1/annotations/${annotationId}`, {
  228 |       headers: { Authorization: `Bearer ${token}` }
  229 |     })
  230 |   })
  231 | 
  232 |   test('TC-ANN-API-007: 创建和查询 relationship annotation', async ({ request }) => {
  233 |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  234 |       data: { username: 'admin', password: 'admin123' }
  235 |     })
  236 |     const loginData = await loginResponse.json()
  237 |     const token = loginData.data?.token
  238 | 
  239 |     // 创建 annotation
  240 |     const createResponse = await request.post(`${BASE_URL}/api/v1/annotations`, {
  241 |       headers: { 
  242 |         Authorization: `Bearer ${token}`,
  243 |         'Content-Type': 'application/json'
  244 |       },
  245 |       data: {
  246 |         target_type: 'relationship',
  247 |         target_id: 1,
  248 |         category: 'warning',
  249 |         content: 'E2E测试 - 关系警告备注'
  250 |       }
  251 |     })
  252 | 
  253 |     expect(createResponse.ok()).toBeTruthy()
  254 |     const createData = await createResponse.json()
  255 |     expect(createData.success).toBe(true)
  256 |     const annotationId = createData.data.id
  257 | 
  258 |     console.log(`✅ 创建 relationship annotation: ID=${annotationId}`)
  259 | 
  260 |     // 更新 annotation
  261 |     const updateResponse = await request.put(`${BASE_URL}/api/v1/annotations/${annotationId}`, {
  262 |       headers: { 
  263 |         Authorization: `Bearer ${token}`,
  264 |         'Content-Type': 'application/json'
  265 |       },
  266 |       data: {
  267 |         category: 'important',
  268 |         content: 'E2E测试 - 更新后的关系备注'
  269 |       }
  270 |     })
  271 | 
  272 |     expect(updateResponse.ok()).toBeTruthy()
  273 |     const updateData = await updateResponse.json()
  274 |     expect(updateData.success).toBe(true)
  275 | 
  276 |     console.log('✅ 更新 annotation 成功')
  277 | 
  278 |     // 清理
  279 |     await request.delete(`${BASE_URL}/api/v1/annotations/${annotationId}`, {
  280 |       headers: { Authorization: `Bearer ${token}` }
  281 |     })
  282 |   })
  283 | })
  284 | 
  285 | test.describe('Annotation UI Tests - Annotation UI 测试', () => {
  286 |   test.beforeEach(async ({ page }) => {
  287 |     await login(page)
  288 |   })
  289 | 
  290 |   test('TC-ANN-UI-001: 服务模块详情页应显示备注面板', async ({ page }) => {
  291 |     // 导航到服务模块管理
  292 |     await page.goto(`${BASE_URL}/service-module-management`)
  293 |     await page.waitForLoadState('networkidle')
  294 |     await page.waitForTimeout(3000)
  295 | 
  296 |     // 等待列表加载
> 297 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  298 |     await page.waitForTimeout(2000)
  299 | 
  300 |     // 点击第一行打开详情
  301 |     const firstRow = page.locator('.el-table__body tr').first()
  302 |     await firstRow.click()
  303 |     await page.waitForTimeout(2000)
  304 | 
  305 |     // 查找详情抽屉
  306 |     const drawer = page.locator('.el-drawer').first()
  307 |     if (await drawer.isVisible()) {
  308 |       // 查找备注信息标签
  309 |       const annotationTab = drawer.locator('.el-tabs__item:has-text("备注"), .anchor-tab:has-text("备注")')
  310 |       
  311 |       if (await annotationTab.count() > 0) {
  312 |         console.log('✅ 服务模块详情页显示"备注信息"标签')
  313 |         
  314 |         // 点击标签
  315 |         await annotationTab.first().click()
  316 |         await page.waitForTimeout(1000)
  317 | 
  318 |         // 验证 AnnotationList 组件
  319 |         const annotationList = drawer.locator('.annotation-list, [class*="annotation"]')
  320 |         if (await annotationList.count() > 0) {
  321 |           console.log('✅ AnnotationList 组件已渲染')
  322 |         }
  323 |       } else {
  324 |         console.log('⚠️ 未找到"备注信息"标签，可能页面结构不同')
  325 |       }
  326 |     } else {
  327 |       console.log('⚠️ 详情抽屉未打开')
  328 |     }
  329 |   })
  330 | 
  331 |   test('TC-ANN-UI-002: 业务对象详情页应显示备注面板', async ({ page }) => {
  332 |     // 导航到业务对象管理
  333 |     await page.goto(`${BASE_URL}/business-object-management`)
  334 |     await page.waitForLoadState('networkidle')
  335 |     await page.waitForTimeout(3000)
  336 | 
  337 |     // 等待列表加载
  338 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  339 |     await page.waitForTimeout(2000)
  340 | 
  341 |     // 点击第一行
  342 |     const firstRow = page.locator('.el-table__body tr').first()
  343 |     await firstRow.click()
  344 |     await page.waitForTimeout(2000)
  345 | 
  346 |     const drawer = page.locator('.el-drawer').first()
  347 |     if (await drawer.isVisible()) {
  348 |       const annotationTab = drawer.locator('.el-tabs__item:has-text("备注"), .anchor-tab:has-text("备注")')
  349 |       
  350 |       if (await annotationTab.count() > 0) {
  351 |         console.log('✅ 业务对象详情页显示"备注信息"标签')
  352 |       }
  353 |     }
  354 |   })
  355 | 
  356 |   test('TC-ANN-UI-003: 关系详情页应显示备注面板', async ({ page }) => {
  357 |     // 导航到关系管理
  358 |     await page.goto(`${BASE_URL}/relationship-management`)
  359 |     await page.waitForLoadState('networkidle')
  360 |     await page.waitForTimeout(3000)
  361 | 
  362 |     // 等待列表加载
  363 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  364 |     await page.waitForTimeout(2000)
  365 | 
  366 |     // 点击第一行
  367 |     const firstRow = page.locator('.el-table__body tr').first()
  368 |     await firstRow.click()
  369 |     await page.waitForTimeout(2000)
  370 | 
  371 |     const drawer = page.locator('.el-drawer').first()
  372 |     if (await drawer.isVisible()) {
  373 |       const annotationTab = drawer.locator('.el-tabs__item:has-text("备注"), .anchor-tab:has-text("备注")')
  374 |       
  375 |       if (await annotationTab.count() > 0) {
  376 |         console.log('✅ 关系详情页显示"备注信息"标签')
  377 |       }
  378 |     }
  379 |   })
  380 | 
  381 |   test('TC-ANN-UI-004: 创建备注功能测试', async ({ page }) => {
  382 |     await page.goto(`${BASE_URL}/service-module-management`)
  383 |     await page.waitForLoadState('networkidle')
  384 |     await page.waitForTimeout(3000)
  385 | 
  386 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  387 |     await page.waitForTimeout(2000)
  388 | 
  389 |     const firstRow = page.locator('.el-table__body tr').first()
  390 |     await firstRow.click()
  391 |     await page.waitForTimeout(2000)
  392 | 
  393 |     const drawer = page.locator('.el-drawer').first()
  394 |     if (await drawer.isVisible()) {
  395 |       const annotationTab = drawer.locator('.el-tabs__item:has-text("备注"), .anchor-tab:has-text("备注")')
  396 |       
  397 |       if (await annotationTab.count() > 0) {
```