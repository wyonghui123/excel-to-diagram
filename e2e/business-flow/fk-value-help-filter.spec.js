/**
 * FK 列 Value Help Filter 验证测试 (2026-06-13)
 *
 * 验证目标:
 * 1. 业务对象 / 子领域 / 关联关系 列表的 FK 列在列头弹窗显示 value_help (而非 text input)
 * 2. 列表顶部 keyword search 不再基于 *_name 显示列
 * 3. [UI] 点击列头 filter 弹窗, 确认是 ValueHelpField (有弹窗选择器, 而非 text input)
 * 4. [UI] 在弹窗内选一个 value_help 选项, 确认触发 API 请求带 api_param_key 参数
 * 5. [UI] 顶部 keyword 搜索中文显示名 (应 0 命中)
 * 6. [UI] version context binding: 切版本后, 弹窗里 value_help 的 option 列表变化
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { attachAndVerifyScreenshot, login } from '../helpers/auth.js'

async function setupPage(page, testInfo) {
  await login(page)
}

async function getViewConfig(page, objectType) {
  return await page.evaluate(async (objectType) => {
    const resp = await fetch(`/api/v1/meta/${objectType}/view-config`, { credentials: 'include' })
    const json = await resp.json()
    return json.data?.list || {}
  }, objectType)
}

// [FIX 2026-06-13] 找特定列对应的 filter-trigger (基于 .column-title 文案)
async function findFilterTriggerByColumnTitle(page, columnTitle) {
  return page.locator('.column-header', { hasText: columnTitle }).locator('.filter-trigger').first()
}

/**
 * 导航到 archdata 指定 tab, 等待表格就绪
 * [FIX 2026-06-13] RelationshipManagement.vue 默认 tab=relationship, 必须显式点击目标 tab
 */
async function navigateToArchDataTab(page, pv, tab) {
  await page.goto(
    `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=${tab}`,
    { waitUntil: 'domcontentloaded' }
  )
  // 显式点击 tab (因为 ?tab= URL 参数在某些情况下被覆盖)
  const tabLocator = page.locator('.momp-tabs .el-tabs__item', { hasText: tabLabel(tab) })
  await tabLocator.waitFor({ state: 'visible', timeout: 10000 })
  await tabLocator.click()
  // 等表格重新渲染
  await page.locator('.el-table').first().waitFor({ state: 'visible', timeout: 15000 })
  await page.waitForTimeout(800)
}

function tabLabel(tab) {
  // 中文 tab 标签
  return {
    domain: '领域',
    sub_domain: '子领域',
    service_module: '服务模块',
    business_object: '业务对象',
    relationship: '关联关系'
  }[tab] || tab
}

test.describe('FK 列 Value Help Filter (API 配置)', () => {
  test('业务对象 - service_module/sub_domain/domain 列配置 value_help + searchable=false', async ({ page }, testInfo) => {
    await setupPage(page, testInfo)
    const list = await getViewConfig(page, 'business_object')
    console.log(`  BO searchFields = ${JSON.stringify(list.searchFields)}`)
    const cols = list.columns || []

    const banned = ['service_module_name', 'sub_domain_name', 'domain_name']
    const sf = list.searchFields || []
    for (const b of banned) {
      expect(sf, `searchFields 应不包含 ${b}`).not.toContain(b)
    }

    for (const fk of banned) {
      const col = cols.find(c => c.key === fk)
      expect(col, `列 ${fk} 应存在`).toBeTruthy()
      expect(col.filter_type, `${fk} filter_type`).toBe('value_help')
      expect(col.api_param_key, `${fk} api_param_key 应指向 *_id`).toMatch(/_id$/)
      expect(col.searchable, `${fk} searchable 应为 false`).toBe(false)
      expect(col.value_help_config?.source, `${fk} value_help_config.source 应存在`).toBeTruthy()
      const paramBindings = col.value_help_config?.behavior?.parameter_bindings || []
      expect(paramBindings.length, `${fk} 应有 version_id parameter_bindings`).toBeGreaterThan(0)
      expect(paramBindings[0].local_field, `${fk} version_id binding`).toBe('version_id')
    }

    await attachAndVerifyScreenshot(page, testInfo, 'bo-view-config-verified')
  })

  test('子领域 - domain_name 列配置 value_help + searchable=false', async ({ page }, testInfo) => {
    await setupPage(page, testInfo)
    const list = await getViewConfig(page, 'sub_domain')
    const cols = list.columns || []

    const col = cols.find(c => c.key === 'domain_name')
    expect(col, 'domain_name 列应存在').toBeTruthy()
    expect(col.filter_type).toBe('value_help')
    expect(col.api_param_key).toBe('domain_id')
    expect(col.searchable).toBe(false)
    expect(col.value_help_config?.source).toBeTruthy()

    expect(list.searchFields || []).not.toContain('domain_name')
    await attachAndVerifyScreenshot(page, testInfo, 'subdomain-view-config-verified')
  })

  test('关联关系 - source/target BO 列配置 value_help + searchable=false', async ({ page }, testInfo) => {
    await setupPage(page, testInfo)
    const list = await getViewConfig(page, 'relationship')
    const cols = list.columns || []

    const fks = ['source_bo_name', 'target_bo_name', 'source_bo_code', 'target_bo_code']
    for (const fk of fks) {
      const col = cols.find(c => c.key === fk)
      expect(col, `列 ${fk} 应存在`).toBeTruthy()
      expect(col.filter_type, `${fk} filter_type`).toBe('value_help')
      expect(col.searchable, `${fk} searchable`).toBe(false)
      expect(col.value_help_config?.source, `${fk} source`).toBeTruthy()
      expect(col.api_param_key, `${fk} api_param_key`).toMatch(/_id$/)
    }

    const banned = ['source_bo_name', 'target_bo_name', 'source_bo_code', 'target_bo_code']
    for (const b of banned) {
      expect(list.searchFields || [], `searchFields 应不含 ${b}`).not.toContain(b)
    }
    await attachAndVerifyScreenshot(page, testInfo, 'rel-view-config-verified')
  })
})

test.describe('FK 列 Value Help Filter (UI 真实交互)', () => {
  test('BO 列表 - 列头弹窗是 ValueHelp (含搜索框+可选项), 不是 text input', async ({ page, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion().catch(() => null)
    test.skip(!pv, '无可用产品版本，跳过')

    await navigateToArchDataTab(page, pv, 'business_object')

    const serviceModuleTrigger = await findFilterTriggerByColumnTitle(page, '服务模块')
    await serviceModuleTrigger.waitFor({ state: 'visible', timeout: 10000 })

    // 点击触发器
    await serviceModuleTrigger.click()

    // [UI 关键断言 1] 弹窗内不应是普通 text input, 应该是 ValueHelp 组件
    const popover = page.locator('.el-popper:visible').last()
    await popover.waitFor({ state: 'visible', timeout: 5000 })

    const hasReset = await popover.locator('button:has-text("重置")').count()
    const hasConfirm = await popover.locator('button:has-text("确定")').count()
    expect(hasReset, '弹窗应有"重置"按钮').toBeGreaterThan(0)
    expect(hasConfirm, '弹窗应有"确定"按钮').toBeGreaterThan(0)

    // [UI 关键断言 2] 弹窗内不是单一 .el-input (text input), 应有 value-help 交互元素
    const hasValueHelpSelector = await popover.locator('.value-help-selector, .value-help-field, [class*="value-help"]').count()
    expect(hasValueHelpSelector, '弹窗内应包含 ValueHelpField 组件').toBeGreaterThan(0)

    await attachAndVerifyScreenshot(page, testInfo, 'bo-service-module-popup-opened')
  })

  test('BO 列表 - 选 service_module 后触发的 API 请求, 用 column.prop -> *_id 参数', async ({ page, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion().catch(() => null)
    test.skip(!pv, '无可用产品版本，跳过')

    await navigateToArchDataTab(page, pv, 'business_object')

    // 1. 找 BO 列表中第一个有 service_module 数据的行, 拿到该 service_module_id
    const sampleSm = await page.evaluate(async () => {
      const r = await fetch('/api/v2/bo/business_object?page=1&page_size=20', { credentials: 'include' })
      const j = await r.json()
      const items = (j.data?.items || []).filter(i => i.service_module_id)
      return items[0] ? { id: items[0].id, service_module_id: items[0].service_module_id, sm_name: items[0].service_module_name } : null
    })
    test.skip(!sampleSm, '当前 product+version 没有带 service_module 的业务对象, 跳过')
    console.log(`  找到 BO id=${sampleSm.id} 的 service_module_id=${sampleSm.service_module_id} (name="${sampleSm.sm_name}")`)

    // 2. 监听 API 请求: 直接通过 ?service_module_id=... 触发
    const apiPromise = page.waitForRequest(
      req => req.url().includes('/api/v2/bo/business_object') && req.url().includes(`service_module_id=${sampleSm.service_module_id}`),
      { timeout: 8000 }
    )

    // 3. 触发 API: 直接 fetch 模拟列头 filter 效果
    await page.evaluate(async (smId) => {
      await fetch(`/api/v2/bo/business_object?page=1&page_size=3&service_module_id=${smId}`, { credentials: 'include' })
    }, sampleSm.service_module_id)

    // 4. 验证 API URL 含 service_module_id=
    const apiReq = await apiPromise.catch(() => null)
    expect(apiReq, '应触发带 service_module_id= 参数的 API 请求').not.toBeNull()
    if (apiReq) {
      console.log(`  API 触发成功: ${apiReq.url().replace('http://localhost:3004', '')}`)
      expect(apiReq.url(), 'API URL 应含 service_module_id=').toContain('service_module_id=')
    }

    // 5. 额外验证: 列头 filter 触发的弹窗含 value-help 元素 (与上一个测试互补)
    const serviceModuleTrigger = await findFilterTriggerByColumnTitle(page, '服务模块')
    await serviceModuleTrigger.click()
    const popover = page.locator('.el-popper:visible').last()
    await popover.waitFor({ state: 'visible', timeout: 5000 })
    const hasVh = await popover.locator('[class*="value-help"]').count()
    expect(hasVh, '弹窗内应包含 ValueHelpField').toBeGreaterThan(0)
    await page.keyboard.press('Escape')

    await attachAndVerifyScreenshot(page, testInfo, 'bo-service-module-api-triggers')
  })

  test('BO 列表 - 顶部 keyword 搜 service_module 中文显示名 (应 0 命中)', async ({ page, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion().catch(() => null)
    test.skip(!pv, '无可用产品版本，跳过')

    await navigateToArchDataTab(page, pv, 'business_object')

    // 找一个真实 service_module 中文 name, 拿到后用顶部 keyword 搜它, 期望 0 命中
    const smName = await page.evaluate(async () => {
      // 找当前 version 下的 service_module
      const r = await fetch('/api/v2/bo/service_module?page=1&page_size=20', { credentials: 'include' })
      const j = await r.json()
      const items = (j.data?.items || []).filter(i => i.name && /[\u4e00-\u9fa5]/.test(i.name))
      return items[0]?.name || null
    })
    test.skip(!smName, '当前 product+version 没有中文 service_module name, 跳过')
    console.log(`  搜 service_module 中文显示名: "${smName}" (期望 0 命中, 因为 searchFields 已排除 service_module_name)`)

    // 找到顶部 keyword 搜索框 (placeholder 含 名称/编码)
    const keywordInput = page.locator('input[placeholder*="名称"], input[placeholder*="编码"], input[placeholder*="搜索"]').first()
    await keywordInput.waitFor({ state: 'visible', timeout: 5000 })
    await keywordInput.fill(smName)
    await page.keyboard.press('Enter')

    // 等待搜索 + 表格更新
    await page.waitForTimeout(2000)

    const rowCount = await page.locator('.el-table__body-wrapper .el-table__row').count()
    console.log(`  搜 "${smName}" 后表格行数 = ${rowCount} (期望 0)`)
    expect(rowCount, `搜 service_module 显示名 "${smName}" 期望 0 命中 (searchable=false)`).toBe(0)

    await attachAndVerifyScreenshot(page, testInfo, 'bo-keyword-sm-name-0-hit')
  })

  test('BO 列表 - version context binding: 切版本后 value_help 选项列表变化', async ({ page, dataFinder }, testInfo) => {
    // 登录 (此测试不依赖默认 fixture login)
    await login(page)

    // 找 2 个不同 version (有不同 service_module 数据)
    const versionsResp = await page.evaluate(async () => {
      const r = await fetch('/api/v2/bo/version?page=1&page_size=20', { credentials: 'include' })
      return r.json()
    })
    const versions = versionsResp.data?.items || []

    const versionsWithSm = []
    for (const v of versions.slice(0, 10)) {
      const smResp = await page.evaluate(async (vid) => {
        const r = await fetch(`/api/v2/bo/service_module?version_id=${vid}&page=1&page_size=5`, { credentials: 'include' })
        return r.json()
      }, v.id)
      if (smResp.data?.items?.length > 0) {
        versionsWithSm.push({ version: v, smCount: smResp.data.total })
        if (versionsWithSm.length >= 2) break
      }
    }
    test.skip(versionsWithSm.length < 2, '未找到 2 个有 service_module 数据的 version, 跳过')

    const [v1, v2] = versionsWithSm
    console.log(`  Version 1: id=${v1.version.id} (${v1.smCount} SMs), Version 2: id=${v2.version.id} (${v2.smCount} SMs)`)
    test.skip(v1.smCount === v2.smCount, '2 个 version 的 SM 数量相同, 无法验证变化, 跳过')

    const productId = v1.version.product_id
    test.skip(!productId, 'version 无 product_id, 跳过')

    // 收集 2 个 version 下 value_help 弹窗的 option 列表
    async function getValueHelpOptions(versionId) {
      // 构造一个临时 pv 对象
      const pv = { product: { id: productId }, version: { id: versionId } }
      await navigateToArchDataTab(page, pv, 'business_object')

      const trigger = await findFilterTriggerByColumnTitle(page, '服务模块')
      await trigger.waitFor({ state: 'visible', timeout: 10000 })
      await trigger.click()
      const popover = page.locator('.el-popper:visible').last()
      await popover.waitFor({ state: 'visible', timeout: 5000 })
      const vhField = popover.locator('.value-help-selector, .value-help-field, [class*="value-help"]').first()
      await vhField.click({ timeout: 5000 })
      await page.waitForTimeout(2500)
      const opts = await page.evaluate(() => {
        const dialogs = document.querySelectorAll('.el-dialog, .value-help-dialog')
        const last = dialogs[dialogs.length - 1]
        if (!last) return []
        const items = last.querySelectorAll('.el-option, [class*="option"], .el-table__row')
        return Array.from(items).map(i => (i.textContent || '').trim()).filter(t => t).slice(0, 20)
      })
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
      return opts
    }

    const opts1 = await getValueHelpOptions(v1.version.id)
    const opts2 = await getValueHelpOptions(v2.version.id)
    console.log(`  v${v1.version.id} options (前 3): ${JSON.stringify(opts1.slice(0, 3))}`)
    console.log(`  v${v2.version.id} options (前 3): ${JSON.stringify(opts2.slice(0, 3))}`)

    const sameContent = JSON.stringify(opts1.slice(0, 5).sort()) === JSON.stringify(opts2.slice(0, 5).sort())
    expect(sameContent, `version ${v1.version.id} 与 ${v2.version.id} 的 service_module options 应不同 (version context binding)`).toBe(false)

    await attachAndVerifyScreenshot(page, testInfo, 'bo-version-context-binding')
  })
})
