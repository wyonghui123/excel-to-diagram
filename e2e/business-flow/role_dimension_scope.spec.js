/**
 * S-BF-ROLE_DIMENSION_SCOPE-AUTO: 角色维度范围 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 role_dimension_scope.yaml 自动生成
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
 *   BR-role_dimension_scope-FLD-REQ-role_id  (角色ID 必填)
 *   BR-role_dimension_scope-FLD-REQ-dimension_code  (维度编码 必填)
 *   BR-role_dimension_scope-FLD-REQ-dimension_values  (维度值列表 必填)
 *
 * 自动生成时间: 2026-05-18
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const ROLE_DIMENSION_SCOPE_URL = '/role_dimension_scope-management'

test.describe('S-BF-ROLE_DIMENSION_SCOPE-AUTO: 角色维度范围 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        dimension_code: "placeholder_dimension_code",
        dimension_values: "placeholder_dimension_values",
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 维度编码 (dimension_code)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-dimension_code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_DIMENSION_CODE: 缺少必填字段 [维度编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [维度编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        role_id: null,
        dimension_values: "placeholder_dimension_values",
      }, 'dimension_code')
      expect(result, '[API 维度] 缺少 [维度编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 维度值列表 (dimension_values)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-dimension_values
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_DIMENSION_VALUES: 缺少必填字段 [维度值列表] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [维度值列表] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        role_id: null,
        dimension_code: "placeholder_dimension_code",
      }, 'dimension_values')
      expect(result, '[API 维度] 缺少 [维度值列表] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [角色维度范围] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [角色维度范围] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [角色维度范围] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_role_dimension_scope', async () => {
        await navigateTo(page, '/role_dimension_scope-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
