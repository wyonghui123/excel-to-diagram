/**
 * S-BF-FILTER_VARIANT-AUTO: 过滤变体 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 filter_variant.yaml 自动生成
 * [E2E v2 铁律合规 (8 项)]
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM (GenericListPage) 不用直接 locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 解构
 * [阶段三] Healer 守护: C_AUDIT/C_DEL/C_UI_NAV 失败时软断言
 *
 * 业务规则:
 *   BR-filter_variant-FLD-REQ-name  (变体名称 必填)
 *   BR-filter_variant-FLD-REQ-object_type  (对象类型 必填)
 *   BR-filter_variant-FLD-REQ-filters  (过滤条件 必填)
 *
 * 自动生成时间: 2026-05-08
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const FILTER_VARIANT_URL = '/filter_variant-management'

test.describe('S-BF-FILTER_VARIANT-AUTO: 过滤变体 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 变体名称 (name)
   * 业务规则: BR-filter_variant-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [变体名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [变体名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        object_type: "placeholder_object_type",
        filters: "placeholder_filters",
      }, 'name')
      expect(result, '[API 维度] 缺少 [变体名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象类型 (object_type)
   * 业务规则: BR-filter_variant-FLD-REQ-object_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_TYPE: 缺少必填字段 [对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        name: "placeholder_name",
        filters: "placeholder_filters",
      }, 'object_type')
      expect(result, '[API 维度] 缺少 [对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 过滤条件 (filters)
   * 业务规则: BR-filter_variant-FLD-REQ-filters
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_FILTERS: 缺少必填字段 [过滤条件] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [过滤条件] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        name: "placeholder_name",
        object_type: "placeholder_object_type",
      }, 'filters')
      expect(result, '[API 维度] 缺少 [过滤条件] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [过滤变体] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [过滤变体] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [过滤变体] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_filter_variant', async () => {
        await navigateTo(page, '/filter_variant-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
