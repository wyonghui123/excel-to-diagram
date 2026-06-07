# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: association-metadata.spec.js >> Association API Integration - 关联 API 集成测试 >> TC-ASSOC-API-003: Role UI Config 应返回 users 和 assigned_groups 关联
- Location: e2e\association-metadata.spec.js:511:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
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
  512 |     const loginResponse = await request.post('/api/v1/auth/login', {
  513 |       data: { username: 'admin', password: 'admin123' }
  514 |     })
  515 |     const loginData = await loginResponse.json()
  516 |     const token = loginData.data?.token
  517 | 
  518 |     const uiConfigResponse = await request.get('/api/v2/meta/role/ui-config', {
  519 |       headers: { Authorization: `Bearer ${token}` }
  520 |     })
  521 | 
> 522 |     expect(uiConfigResponse.ok()).toBeTruthy()
      |                                   ^ Error: expect(received).toBeTruthy()
  523 |     const uiConfig = await uiConfigResponse.json()
  524 |     expect(uiConfig.success).toBe(true)
  525 | 
  526 |     const associations = uiConfig.data.associations || []
  527 |     console.log(`\n=== Role Associations (${associations.length}) ===`)
  528 | 
  529 |     for (const assoc of associations) {
  530 |       console.log(`\n${assoc.name}:`)
  531 |       console.log(`  - target_type: ${assoc.target_type}`)
  532 |       console.log(`  - type: ${assoc.type}`)
  533 |       console.log(`  - display.label: ${assoc.display.label}`)
  534 |       console.log(`  - columns: ${(assoc.display.columns || []).length} 个`)
  535 |       console.log(`  - readonly: ${assoc.readonly || false}`)
  536 |       console.log(`  - confirm_message: ${assoc.actions?.unassign?.confirm_message || 'N/A'}`)
  537 |     }
  538 | 
  539 |     // 验证 users 关联
  540 |     const usersAssoc = associations.find(a => a.name === 'users')
  541 |     expect(usersAssoc).toBeDefined()
  542 |     if (usersAssoc) {
  543 |       expect(usersAssoc.display.columns).toBeDefined()
  544 |       expect(usersAssoc.display.columns.length).toBeGreaterThanOrEqual(2)
  545 |     }
  546 | 
  547 |     // 验证 assigned_groups 关联
  548 |     const groupsAssoc = associations.find(a => a.name === 'assigned_groups')
  549 |     expect(groupsAssoc).toBeDefined()
  550 |     if (groupsAssoc) {
  551 |       expect(groupsAssoc.readonly).toBe(true)
  552 |     }
  553 | 
  554 |     console.log('\n✅ Role UI Config associations 验证通过')
  555 |   })
  556 | })
  557 | 
```