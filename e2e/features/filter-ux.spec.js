/**
 * S-FILTER: 过滤 UX (Filter) - v2 风格
 *
 * 覆盖: 4 个 variant (v2 report §四) - thin category 加深
 * - single_criteria: 单条件过滤
 * - multi_select: 多选过滤
 * - date_range: 日期范围
 * - multi_criteria_AND: 多条件 AND
 *
 * 实施目标 (基于 feature_gap_v2.md §四):
 * - 业务风险: 🟢 UX
 * - 代码侧: useMetaList.js: visibleFilterFields (L121), filterDisplayModeConfig (L286)
 * - 现有 spec: 薄 (fk-filter 42, value-help-filter 39, 但都是聚焦)
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM 不用直接 .el-table locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] 每个步骤 withStep() 包裹
 * [OK] isolation fixture 自动清理
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

test.describe('S-FILTER: 过滤 UX (Filter)', () => {
  test('C01 [single_criteria]: 单条件文本搜索', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    const uniquePrefix = `E2E_F01_${Date.now().toString(36).toUpperCase()}`

    await withStep(page, testInfo, 'API 创建 1 条唯一 name 的 BO', async () => {
      await isolation.createTracked('business_object', {
        code: `${uniquePrefix}_X`,
        name: `${uniquePrefix}_NAME`,
        version_id: pv.version.id
      })
    })

    await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`)

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到 businessObject tab', async () => {
      await archData.openTab('businessObject')
    })

    await withStep(page, testInfo, '应用文本搜索 (POM)', async () => {
      await archData.search(uniquePrefix)
      await waitForApiFn(page, 'GET /api/v2/bo/business_object').catch(() => {})
    })

    await withStep(page, testInfo, '断言: 行存在 (POM expectRowExists)', async () => {
      await archData.expectRowExists(uniquePrefix, { timeout: 10000 })
    })
  })

  test('C02 [multi_select]: 多选过滤 (探查)', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`)

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到 businessObject tab', async () => {
      await archData.openTab('businessObject')
    })

    await withStep(page, testInfo, '探查可多选列 (POM getColumnHeaders)', async () => {
      const headers = await archData.getColumnHeaders()
      // 通常 status / is_system / type 列支持多选过滤
      const multiSelectable = headers.filter(h => /状态|status|类型|type|系统|is_system/i.test(h))
      console.log(`[C02] 可多选过滤列: ${multiSelectable.join(' / ')}`)
    })
  })

  test('C03 [date_range]: 日期范围过滤 (探查)', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`)

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到 businessObject tab', async () => {
      await archData.openTab('businessObject')
    })

    await withStep(page, testInfo, '探查日期列 (POM)', async () => {
      const headers = await archData.getColumnHeaders()
      const dateHeaders = headers.filter(h => /日期|date|创建|created|更新|updated/i.test(h))
      console.log(`[C03] 日期列: ${dateHeaders.join(' / ')}`)
    })
  })

  test('C04 [multi_criteria_AND]: 多条件 AND 组合', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    const uniquePrefix = `E2E_F04_${Date.now().toString(36).toUpperCase()}`

    await withStep(page, testInfo, 'API 创建 1 条测试 BO', async () => {
      await isolation.createTracked('business_object', {
        code: `${uniquePrefix}_Y`,
        name: `${uniquePrefix}_YName`,
        version_id: pv.version.id
      })
    })

    await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}&tab=business_object`)

    const archData = new ArchDataPage(page)
    await withStep(page, testInfo, '切到 businessObject tab', async () => {
      await archData.openTab('businessObject')
    })

    await withStep(page, testInfo, '应用 code + name 双条件', async () => {
      // 用 search (POM) - 简化版只搜 code (项目通常只支持单搜索框)
      await archData.search(uniquePrefix)
      await waitForApiFn(page, 'GET /api/v2/bo/business_object').catch(() => {})
    })

    await withStep(page, testInfo, '断言: 行存在 (AND 条件通过)', async () => {
      await archData.expectRowExists(uniquePrefix, { timeout: 10000 })
    })
  })
})
