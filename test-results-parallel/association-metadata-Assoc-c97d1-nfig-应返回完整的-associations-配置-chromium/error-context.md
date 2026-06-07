# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: association-metadata.spec.js >> Association API Integration - 关联 API 集成测试 >> TC-ASSOC-API-001: UI Config 应返回完整的 associations 配置
- Location: e2e\association-metadata.spec.js:402:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
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
  364 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
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
> 411 |     expect(loginResponse.ok()).toBeTruthy()
      |                                ^ Error: expect(received).toBeTruthy()
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
  465 |     const loginResponse = await request.post('/api/v1/auth/login', {
  466 |       data: { username: 'admin', password: 'admin123' }
  467 |     })
  468 |     const loginData = await loginResponse.json()
  469 |     const token = loginData.data?.token
  470 | 
  471 |     const uiConfigResponse = await request.get('/api/v2/meta/user_group/ui-config', {
  472 |       headers: { Authorization: `Bearer ${token}` }
  473 |     })
  474 | 
  475 |     expect(uiConfigResponse.ok()).toBeTruthy()
  476 |     const uiConfig = await uiConfigResponse.json()
  477 |     expect(uiConfig.success).toBe(true)
  478 | 
  479 |     const associations = uiConfig.data.associations || []
  480 |     console.log(`\n=== UserGroup Associations (${associations.length}) ===`)
  481 | 
  482 |     // 验证 members 关联
  483 |     const membersAssoc = associations.find(a => a.name === 'members')
  484 |     if (membersAssoc) {
  485 |       console.log(`\nMembers association:`)
  486 |       console.log(`  - target_type: ${membersAssoc.target_type}`)
  487 |       console.log(`  - display.label: ${membersAssoc.display.label}`)
  488 |       console.log(`  - columns: ${(membersAssoc.display.columns || []).length} 个`)
  489 |       console.log(`  - confirm_message: ${membersAssoc.actions?.unassign?.confirm_message}`)
  490 |       
  491 |       expect(membersAssoc.display.columns).toBeDefined()
  492 |       expect(membersAssoc.display.columns.length).toBeGreaterThanOrEqual(2)
  493 |     }
  494 | 
  495 |     // 验证 roles 关联
  496 |     const rolesAssoc = associations.find(a => a.name === 'roles')
  497 |     if (rolesAssoc) {
  498 |       console.log(`\nRoles association:`)
  499 |       console.log(`  - target_type: ${rolesAssoc.target_type}`)
  500 |       console.log(`  - display.label: ${rolesAssoc.display.label}`)
  501 |       console.log(`  - columns: ${(rolesAssoc.display.columns || []).length} 个`)
  502 |       console.log(`  - confirm_message: ${rolesAssoc.actions?.unassign?.confirm_message}`)
  503 |       
  504 |       expect(rolesAssoc.display.columns).toBeDefined()
  505 |       expect(rolesAssoc.display.columns.length).toBeGreaterThanOrEqual(2)
  506 |     }
  507 | 
  508 |     console.log('\n✅ UserGroup UI Config associations 验证通过')
  509 |   })
  510 | 
  511 |   test('TC-ASSOC-API-003: Role UI Config 应返回 users 和 assigned_groups 关联', async ({ request }) => {
```