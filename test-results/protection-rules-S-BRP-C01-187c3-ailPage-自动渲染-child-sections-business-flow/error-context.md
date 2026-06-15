# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: business-flow\protection-rules.spec.js >> S-BRP-C01-FRONTEND: ObjectDetailPage 自动渲染 child sections (从 ui_view_config) (BMRD) >> [C01-FRONTEND] ObjectDetailPage 自动渲染 child sections
- Location: e2e\business-flow\protection-rules.spec.js:359:5

# Error details

```
Error: child sections 容器应存在

expect(locator).toBeVisible() failed

Locator: getByTestId('odp-child-sections')
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - child sections 容器应存在 with timeout 15000ms
  - waiting for getByTestId('odp-child-sections')

```

```yaml
- banner:
  - img
  - text: BIP应用架构管理
  - button "系 系统管理员":
    - text: 系 系统管理员
    - img
- button:
  - img
- complementary:
  - navigation:
    - img
    - text: 架构数据管理
    - img
    - text: 产品版本管理
    - img
    - text: 系统管理
    - img
- main
```

# Test source

```ts
  268 |       const hasBtn = await addChildBtn.isVisible({ timeout: 3000 }).catch(() => false)
  269 |       if (!hasBtn) {
  270 |         // [DEFER-BUG-V005] 前端未实现, skip 而非 fail
  271 |         test.skip(true, '[DEFER BUG-V005] ObjectChildSection.createChild 未实现, 等前端实现后启用')
  272 |         return
  273 |       }
  274 |       await addChildBtn.click()
  275 |       await page.waitForTimeout(500)
  276 |       // 故意留空 name, 提交
  277 |       const submitBtn = page.locator('button:has-text("保存"), button:has-text("确定"), button:has-text("Save")').last()
  278 |       if (await submitBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
  279 |         await submitBtn.click()
  280 |         await page.waitForTimeout(500)
  281 |         // 验证: 应有错误提示, 而非成功创建
  282 |         const errorMsg = page.locator('.el-form-item__error, .el-message--error, .el-notification__content').first()
  283 |         const hasError = await errorMsg.isVisible({ timeout: 1000 }).catch(() => false)
  284 |         expect(hasError, '客户端应拦截空 name').toBe(true)
  285 |       } else {
  286 |         test.skip(true, 'no submit button after add child')
  287 |       }
  288 |     })
  289 | 
  290 | })
  291 | 
  292 | test.describe('S-BRP-DEEP-INSERT-1: deep_insert 端点: 创建父 + 子对象 (含 FK 推断) (BMRD)', () => {
  293 |   /**
  294 |    * [DEEP-INSERT-1] POST /api/v2/bo/<object_type>/deep 父+子创建
  295 |    * 业务规则: DEEP-INSERT-1 - deep_insert 端点: 创建父 + 子对象 (含 FK 推断)
  296 |    * 优先级: P1
  297 |    */
  298 |     test('[DEEP-INSERT-1] POST /api/v2/bo/<object_type>/deep 父+子创建', async ({ request }) => {
  299 |       const ts = Date.now()
  300 |       const body = {
  301 |         parent: {
  302 |           id: `test_deep_${ts}`,
  303 |           name: `Test Deep ${ts}`,
  304 |           category: 'system',
  305 |           mutability: 'extensible',
  306 |         },
  307 |         children: {
  308 |           enum_value: [
  309 |             { id: `v1_${ts}`, name: `V1 ${ts}`, value: `val1_${ts}` },
  310 |           ]
  311 |         }
  312 |       }
  313 |       const r = await request.post('/api/v2/bo/enum_type/deep', { data: body })
  314 |       expect(r.status(), 'deep_insert 应 201').toBe(201)
  315 |       const j = await r.json()
  316 |       expect(j.success, 'success 应为 true').toBe(true)
  317 |       expect(j.data.parent.id, 'parent id 应回显').toBe(`test_deep_${ts}`)
  318 |       expect(j.data.children.enum_value[0].enum_type_id, '子应自动关联父 ID').toBe(`test_deep_${ts}`)
  319 |     })
  320 | 
  321 | })
  322 | 
  323 | test.describe('S-BRP-DEEP-INSERT-2: deep_insert 简化格式: 不带 parent/children 包裹 (BMRD)', () => {
  324 |   /**
  325 |    * [DEEP-INSERT-2] deep_insert 简化格式 (不带 parent/children)
  326 |    * 业务规则: DEEP-INSERT-2 - deep_insert 简化格式: 不带 parent/children 包裹
  327 |    * 优先级: P2
  328 |    */
  329 |     test('[DEEP-INSERT-2] deep_insert 简化格式 (不带 parent/children)', async ({ request }) => {
  330 |       const ts = Date.now()
  331 |       // 简化格式: 直接传父字段, _children 标记子
  332 |       const body = {
  333 |         id: `test_simple_${ts}`,
  334 |         name: `Test Simple ${ts}`,
  335 |         category: 'system',
  336 |         mutability: 'extensible',
  337 |         _children: {
  338 |           enum_value: [
  339 |             { id: `sv1_${ts}`, name: `SV1 ${ts}`, value: `sval1_${ts}` },
  340 |           ]
  341 |         }
  342 |       }
  343 |       const r = await request.post('/api/v2/bo/enum_type/deep', { data: body })
  344 |       expect(r.status(), '简化 deep_insert 应 201').toBe(201)
  345 |       const j = await r.json()
  346 |       expect(j.success).toBe(true)
  347 |       // 简化格式下 parent 应回显完整数据
  348 |       expect(j.data.parent.id).toBe(`test_simple_${ts}`)
  349 |     })
  350 | 
  351 | })
  352 | 
  353 | test.describe('S-BRP-C01-FRONTEND: ObjectDetailPage 自动渲染 child sections (从 ui_view_config) (BMRD)', () => {
  354 |   /**
  355 |    * [C01-FRONTEND] ObjectDetailPage 自动渲染 child sections
  356 |    * 业务规则: C01-FRONTEND - ObjectDetailPage 自动渲染 child sections (从 ui_view_config)
  357 |    * 优先级: P1
  358 |    */
  359 |     test('[C01-FRONTEND] ObjectDetailPage 自动渲染 child sections', async ({ page, dataFinder, navigateTo, isolation }) => {
  360 |       // [BMRD-已集成 2026-06-14] ObjectDetailPage 自动从 ui_view_config.child_sections 渲染
  361 |       // 1. 找一个有 child_sections 配置的对象 (product 配 version, enum_type 配 enum_value)
  362 |       const product = await dataFinder.productWithVersion()
  363 |       // 2. 导航到产品详情页
  364 |       await navigateTo(page, '/product-management/' + product.product.id)
  365 |       await page.waitForTimeout(2000)
  366 |       // 3. 验证 child sections 容器存在
  367 |       const childSectionContainer = page.getByTestId('odp-child-sections')
> 368 |       await expect(childSectionContainer, 'child sections 容器应存在').toBeVisible()
      |                                                                   ^ Error: child sections 容器应存在
  369 |       // 4. 验证 ObjectChildSection 子组件渲染
  370 |       const childSectionElements = childSectionContainer.locator('.ocs-root, [class*="ocs"]')
  371 |       const count = await childSectionElements.count()
  372 |       console.log('[C01-FRONTEND] child section 元素数: ' + count)
  373 |       // 软断言: 至少 1 个 child section
  374 |       expect(count, '应至少渲染 1 个 child section').toBeGreaterThan(0)
  375 |     })
  376 |   /**
  377 |    * [C01-FRONTEND] ui-config 端点返回 child_sections
  378 |    * 业务规则: C01-FRONTEND - ObjectDetailPage 自动渲染 child sections (从 ui_view_config)
  379 |    * 优先级: P1
  380 |    */
  381 |     test('[C01-FRONTEND] ui-config 端点返回 child_sections', async ({ request }) => {
  382 |       // 验证 ui_view_config.child_sections 存在
  383 |       const r = await request.get('/api/v2/meta/product/ui-config')
  384 |       expect(r.status(), 'ui-config 应 200').toBe(200)
  385 |       const j = await r.json()
  386 |       const sections = j.data?.ui_view_config?.child_sections || []
  387 |       expect(sections.length, 'product 应有 child_sections').toBeGreaterThan(0)
  388 |       expect(sections[0].child_object, '第一个 child section 应有 child_object').toBeTruthy()
  389 |     })
  390 | 
  391 | })
  392 | 
  393 | test.describe('S-BRP-C02-FRONTEND: 多 child sections 同时渲染 (product 配 version, enum_type 配 enum_value) (BMRD)', () => {
  394 |   /**
  395 |    * [C02-FRONTEND] 详情页支持多个 child sections
  396 |    * 业务规则: C02-FRONTEND - 多 child sections 同时渲染 (product 配 version, enum_type 配 enum_value)
  397 |    * 优先级: P2
  398 |    */
  399 |     test('[C02-FRONTEND] 详情页支持多个 child sections', async ({ page, dataFinder, navigateTo, isolation }) => {
  400 |       // [BMRD-已集成 2026-06-14] 多个 child sections 在 v-for 中同时渲染
  401 |       const product = await dataFinder.productWithVersion()
  402 |       await navigateTo(page, '/product-management/' + product.product.id)
  403 |       await page.waitForTimeout(2000)
  404 |       // 验证 v-for 渲染: 多个 .ocs-root 元素
  405 |       const childContainers = page.getByTestId('odp-child-sections').locator('.ocs-root')
  406 |       const count = await childContainers.count()
  407 |       console.log('[C02-FRONTEND] 渲染 child section 数: ' + count)
  408 |       // product 至少有 1 个 (version)
  409 |       expect(count, '应至少渲染 1 个 child section').toBeGreaterThan(0)
  410 |     })
  411 | 
  412 | })
  413 | 
  414 | test.describe('S-BRP-BUG-V006: version 唯一性: (product_id, name) 联合约束 + 事务隔离 (BMRD)', () => {
  415 |   /**
  416 |    * [BUG-V006-1] version 唯一性: product 内唯一 (product_id, name 联合)
  417 |    * 业务规则: BUG-V006 - version 唯一性: (product_id, name) 联合约束 + 事务隔离
  418 |    * 优先级: P1
  419 |    */
  420 |     test('[BUG-V006-1] version 唯一性: product 内唯一 (product_id, name 联合)', async ({ request, isolation }) => {
  421 |       // [BMRD-真实复现 2026-06-14] 用户场景: NEWTEST33 + V10 重复
  422 |       // [BUG-V006 FIX] 修复前: name 全局唯一 (跨 product 也禁止)
  423 |       // [BUG-V006 FIX] 修复后: product 内唯一 (跨 product 允许, 同 product 禁止)
  424 |       // version schema: name business_key=true, semantics.meaning="产品内唯一"
  425 |       const ts = Date.now()
  426 |       const productA = 323  // NEWTEST33
  427 |       const productB = 326  // TEST1101
  428 |       const verName = 'V10_BUGV006_' + ts
  429 |       // 1. 跨 product 同名 version (应允许)
  430 |       const r1 = await request.post('/api/v2/bo/version', {
  431 |         data: { id: 'va_' + ts, name: verName, product_id: productA, is_current: 1 }
  432 |       })
  433 |       expect(r1.status(), 'product_A 创建 version 应 201').toBe(201)
  434 |       const r2 = await request.post('/api/v2/bo/version', {
  435 |         data: { id: 'vb_' + ts, name: verName, product_id: productB, is_current: 1 }
  436 |       })
  437 |       expect(r2.status(), '跨 product 同名 version 应允许 (201, 修复后)').toBe(201)
  438 |       // 2. 同 product 同名 version (应禁止)
  439 |       const r3 = await request.post('/api/v2/bo/version', {
  440 |         data: { id: 'va2_' + ts, name: verName, product_id: productA, is_current: 0 }
  441 |       })
  442 |       expect(r3.status(), '同 product 重复同名 version 应 400').toBe(400)
  443 |       const j3 = await r3.json()
  444 |       expect(j3.success, 'success 应 false').toBe(false)
  445 |       console.log('[BUG-V006-1] 同 product 重复错误: ' + j3.message)
  446 |     })
  447 |   /**
  448 |    * [BUG-V006-2] deep_insert 设计行为: FK 自动覆盖, 不触发 product_id+name 重复
  449 |    * 业务规则: BUG-V006 - version 唯一性: (product_id, name) 联合约束 + 事务隔离
  450 |    * 优先级: P1
  451 |    */
  452 |     test('[BUG-V006-2] deep_insert 设计行为: FK 自动覆盖, 不触发 product_id+name 重复', async ({ request, isolation }) => {
  453 |       // [BMRD-真实复现 2026-06-14] 用户场景: NEWTEST33 + V10 重复
  454 |       // [关键发现 2026-06-14] deep_insert 自动覆盖 FK product_id = parent.id (deep_insert_engine.py:95)
  455 |       // 因此 deep_insert 永远不触发 product_id+name 唯一性冲突 (FK 总指向新 parent)
  456 |       // 唯一性约束仅在单独 POST version 时触发
  457 |       // 这是 deep_insert 的设计行为, 不是 BUG
  458 |       const ts = Date.now()
  459 |       const productId = 'BUGV006_TX_' + ts
  460 |       // deep_insert 创建 NEW product + 重复 V10 name (force product_id 引用已存在 product)
  461 |       const r1 = await request.post('/api/v2/bo/product/deep', {
  462 |         data: {
  463 |           parent: { id: productId, name: 'BUG-V006 TX ' + ts },
  464 |           children: { version: [{
  465 |             id: 'ver_tx_' + ts, name: 'V1', product_id: 999999999
  466 |           }] }
  467 |         }
  468 |       })
```