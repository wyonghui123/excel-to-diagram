/**
 * FK 列 Value Help Filter 验证测试 (2026-06-13)
 *
 * 验证目标:
 * 1. 业务对象 / 子领域 / 关联关系 列表的 FK 列在列头弹窗显示 value_help (而非 text input)
 * 2. 列表顶部 keyword search 不再基于 *_name 显示列
 *
 * 策略: 简化测试, 直接通过 page.evaluate 检查 store 中的 view_config,
 *       并截屏列表页验证 UI 行为.
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { attachAndVerifyScreenshot } from '../helpers/auth.js'
import { login } from '../helpers/auth.js'

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

test.describe('FK 列 Value Help Filter (API 配置)', () => {
  test('业务对象 - service_module/sub_domain/domain 列配置 value_help + searchable=false', async ({ page }, testInfo) => {
    await setupPage(page, testInfo)
    const list = await getViewConfig(page, 'business_object')
    console.log(`  BO searchFields = ${JSON.stringify(list.searchFields)}`)
    const cols = list.columns || []

    // 期望 searchFields 不包含 *_name
    const banned = ['service_module_name', 'sub_domain_name', 'domain_name']
    const sf = list.searchFields || []
    for (const b of banned) {
      expect(sf, `searchFields 应不包含 ${b}`).not.toContain(b)
    }

    // 期望 3 个 FK 列都有 value_help_config
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

test.describe('FK 列 Value Help Filter (UI 列头弹窗)', () => {
  test('业务对象列表 - 表格含 .filter-trigger 图标 (列头 value_help 入口)', async ({ page, dataFinder }, testInfo) => {
    const pv = await dataFinder.productWithVersion().catch(() => null)
    test.skip(!pv, '无可用产品版本，跳过')

    await page.goto(`/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`, { waitUntil: 'domcontentloaded' })

    // 等待表格 + filter trigger 出现
    await page.locator('.el-table').first().waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('.filter-trigger').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})

    // 至少应有 3 个 filter-trigger (对应 3 个 FK 列)
    const triggerCount = await page.locator('.filter-trigger').count()
    console.log(`  BO 表 filter-trigger 数 = ${triggerCount} (期望 >=3)`)
    expect(triggerCount, 'filter-trigger 数量').toBeGreaterThanOrEqual(3)

    await attachAndVerifyScreenshot(page, testInfo, 'bo-list-filter-triggers')
  })
})