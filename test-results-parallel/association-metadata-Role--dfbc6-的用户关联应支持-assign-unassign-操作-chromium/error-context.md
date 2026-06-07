# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: association-metadata.spec.js >> Role Associations - 角色关联测试 >> TC-ASSOC-ROLE-002: 角色的用户关联应支持 assign/unassign 操作
- Location: e2e\association-metadata.spec.js:363:3

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
  264 |     if (await drawer.isVisible()) {
  265 |       const memberTab = drawer.locator('.el-tabs__item:has-text("成员"), .anchor-tab:has-text("成员")')
  266 |       if (await memberTab.count() > 0) {
  267 |         await memberTab.first().click()
  268 |         await page.waitForTimeout(1000)
  269 | 
  270 |         // 监听确认对话框
  271 |         let confirmMessage = ''
  272 |         page.on('dialog', async dialog => {
  273 |           confirmMessage = dialog.message()
  274 |           console.log(`成员移除确认消息: "${confirmMessage}"`)
  275 |           await dialog.dismiss()
  276 |         })
  277 | 
  278 |         const removeBtn = drawer.locator('.association-panel button:has-text("移除")').first()
  279 |         if (await removeBtn.isVisible()) {
  280 |           await removeBtn.click()
  281 |           await page.waitForTimeout(500)
  282 | 
  283 |           // 验证 confirm_message 来自 YAML 配置
  284 |           expect(confirmMessage).toContain('用户组')
  285 |         }
  286 |       }
  287 |     }
  288 |   })
  289 | })
  290 | 
  291 | test.describe('Role Associations - 角色关联测试', () => {
  292 |   test.beforeEach(async ({ page }) => {
  293 |     await login(page)
  294 |     // 导航到角色管理
  295 |     await page.goto(`${BASE_URL}/role-management`)
  296 |     await page.waitForLoadState('networkidle')
  297 |     await page.waitForTimeout(3000)
  298 |   })
  299 | 
  300 |   test('TC-ASSOC-ROLE-001: 角色详情应显示"用户"和"用户组"关联面板', async ({ page }) => {
  301 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  302 |     await page.waitForTimeout(2000)
  303 | 
  304 |     // 打开第一个角色的详情
  305 |     const firstRow = page.locator('.el-table__body tr').first()
  306 |     await firstRow.click()
  307 |     await page.waitForTimeout(2000)
  308 | 
  309 |     const drawer = page.locator('.el-drawer').first()
  310 |     if (await drawer.isVisible()) {
  311 |       // 查找用户标签 (新增的 tab)
  312 |       const userTab = drawer.locator('.el-tabs__item:has-text("用户"), .anchor-tab:has-text("用户")')
  313 |       const groupTab = drawer.locator('.el-tabs__item:has-text("用户组"), .anchor-tab:has-text("用户组")')
  314 | 
  315 |       const hasUserTab = await userTab.count() > 0
  316 |       const hasGroupTab = await groupTab.count() > 0
  317 | 
  318 |       console.log(`用户标签: ${hasUserTab}, 用户组标签: ${hasGroupTab}`)
  319 | 
  320 |       if (hasUserTab) {
  321 |         await userTab.first().click()
  322 |         await page.waitForTimeout(1000)
  323 | 
  324 |         // 验证用户关联面板
  325 |         const userPanel = drawer.locator('.association-panel').first()
  326 |         if (await userPanel.isVisible()) {
  327 |           console.log('✅ 用户关联面板已渲染')
  328 | 
  329 |           // 验证列定义: username, display_name, email
  330 |           const headers = userPanel.locator('.ap-table th')
  331 |           const headerCount = await headers.count()
  332 |           console.log(`用户表格列数: ${headerCount}`)
  333 | 
  334 |           expect(headerCount).toBeGreaterThanOrEqual(3)
  335 |         }
  336 |       }
  337 | 
  338 |       if (hasGroupTab) {
  339 |         await groupTab.first().click()
  340 |         await page.waitForTimeout(1000)
  341 | 
  342 |         // 验证用户组关联面板 (readonly)
  343 |         const groupPanel = drawer.locator('.association-panel').first()
  344 |         if (await groupPanel.isVisible()) {
  345 |           console.log('✅ 用户组关联面板已渲染')
  346 | 
  347 |           // readonly 的关联不应有添加/移除按钮
  348 |           const addBtn = groupPanel.locator('button:has-text("添加")')
  349 |           const removeBtn = groupPanel.locator('button:has-text("移除")')
  350 |           
  351 |           const hasAddBtn = await addBtn.count() > 0 && await addBtn.isVisible()
  352 |           const hasRemoveBtn = await removeBtn.count() > 0 && await removeBtn.isVisible()
  353 | 
  354 |           console.log(`添加按钮可见: ${hasAddBtn}, 移除按钮可见: ${hasRemoveBtn}`)
  355 |           
  356 |           // assigned_groups 是 readonly，不应该有编辑按钮
  357 |           // 但可能有列表查看功能
  358 |         }
  359 |       }
  360 |     }
  361 |   })
  362 | 
  363 |   test('TC-ASSOC-ROLE-002: 角色的用户关联应支持 assign/unassign 操作', async ({ page }) => {
> 364 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  365 |     await page.waitForTimeout(2000)
  366 | 
  367 |     const firstRow = page.locator('.el-table__body tr').first()
  368 |     await firstRow.click()
  369 |     await page.waitForTimeout(2000)
  370 | 
  371 |     const drawer = page.locator('.el-drawer').first()
  372 |     if (await drawer.isVisible()) {
  373 |       const userTab = drawer.locator('.el-tabs__item:has-text("用户"), .anchor-tab:has-text("用户")')
  374 |       if (await userTab.count() > 0) {
  375 |         await userTab.first().click()
  376 |         await page.waitForTimeout(1000)
  377 | 
  378 |         const userPanel = drawer.locator('.association-panel').first()
  379 |         if (await userPanel.isVisible()) {
  380 |           // 验证添加按钮存在
  381 |           const addBtn = userPanel.locator('button:has-text("添加")')
  382 |           const hasAddBtn = await addBtn.count() > 0
  383 | 
  384 |           console.log(`用户关联添加按钮: ${hasAddBtn}`)
  385 | 
  386 |           if (hasAddBtn && await addBtn.isVisible()) {
  387 |             console.log('✅ 角色用户关联支持 assign 操作')
  388 |           }
  389 | 
  390 |           // 验证移除按钮存在（如果有数据）
  391 |           const removeBtn = userPanel.locator('button:has-text("移除")')
  392 |           if (await removeBtn.count() > 0 && await removeBtn.isVisible()) {
  393 |             console.log('✅ 角色用户关联支持 unassign 操作')
  394 |           }
  395 |         }
  396 |       }
  397 |     }
  398 |   })
  399 | })
  400 | 
  401 | test.describe('Association API Integration - 关联 API 集成测试', () => {
  402 |   test('TC-ASSOC-API-001: UI Config 应返回完整的 associations 配置', async ({ request }) => {
  403 |     // 登录获取 token
  404 |     const loginResponse = await request.post('/api/v1/auth/login', {
  405 |       data: {
  406 |         username: 'admin',
  407 |         password: 'admin123'
  408 |       }
  409 |     })
  410 | 
  411 |     expect(loginResponse.ok()).toBeTruthy()
  412 |     const loginData = await loginResponse.json()
  413 |     const token = loginData.data?.token
  414 | 
  415 |     // 获取 User 的 UI Config
  416 |     const uiConfigResponse = await request.get('/api/v2/meta/user/ui-config', {
  417 |       headers: {
  418 |         Authorization: `Bearer ${token}`
  419 |       }
  420 |     })
  421 | 
  422 |     expect(uiConfigResponse.ok()).toBeTruthy()
  423 |     const uiConfig = await uiConfigResponse.json()
  424 | 
  425 |     console.log('=== User UI Config ===')
  426 |     console.log(`success: ${uiConfig.success}`)
  427 |     
  428 |     expect(uiConfig.success).toBe(true)
  429 |     expect(uiConfig.data).toBeDefined()
  430 |     expect(uiConfig.data.associations).toBeDefined()
  431 | 
  432 |     const associations = uiConfig.data.associations
  433 |     console.log(`Associations 数量: ${associations.length}`)
  434 | 
  435 |     // 验证 groups 关联存在
  436 |     const groupsAssoc = associations.find(a => a.name === 'groups')
  437 |     expect(groupsAssoc).toBeDefined()
  438 |     
  439 |     if (groupsAssoc) {
  440 |       console.log('\n=== Groups Association ===')
  441 |       console.log(`name: ${groupsAssoc.name}`)
  442 |       console.log(`target_type: ${groupsAssoc.target_type}`)
  443 |       console.log(`type: ${groupsAssoc.type}`)
  444 | 
  445 |       // 验证 display 配置
  446 |       expect(groupsAssoc.display).toBeDefined()
  447 |       console.log(`display.label: ${groupsAssoc.display.label}`)
  448 |       expect(groupsAssoc.display.label).toBe('所属用户组')
  449 | 
  450 |       // 验证 columns 配置
  451 |       expect(groupsAssoc.display.columns).toBeDefined()
  452 |       console.log(`columns 数量: ${groupsAssoc.display.columns.length}`)
  453 |       expect(groupsAssoc.display.columns.length).toBeGreaterThanOrEqual(2)
  454 | 
  455 |       // 验证 actions 配置
  456 |       expect(groupsAssoc.actions).toBeDefined()
  457 |       console.log(`actions.unassign.confirm_message: ${groupsAssoc.actions?.unassign?.confirm_message}`)
  458 |       expect(groupsAssoc.actions?.unassign?.confirm_message).toContain('移除')
  459 |     }
  460 | 
  461 |     console.log('\n✅ User UI Config associations 验证通过')
  462 |   })
  463 | 
  464 |   test('TC-ASSOC-API-002: UserGroup UI Config 应返回 members 和 roles 关联', async ({ request }) => {
```