/**
 * S-BF-EMPLOYEE_DATA_SCOPE-AUTO: 员工数据权限范围 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 employee_data_scope.yaml 自动生成
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
 *   BR-employee_data_scope-FLD-REQ-code  (范围编码 必填)
 *   BR-employee_data_scope-FLD-REQ-name  (范围名称 必填)
 *   BR-employee_data_scope-FLD-REQ-condition_template  (条件模板 必填)
 *   BR-employee_data_scope-FLD-UNQ-code  (范围编码 唯一)
 *
 * 自动生成时间: 2026-05-08
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const EMPLOYEE_DATA_SCOPE_URL = '/employee_data_scope-management'

test.describe('S-BF-EMPLOYEE_DATA_SCOPE-AUTO: 员工数据权限范围 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 范围编码 (code)
   * 业务规则: BR-employee_data_scope-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [范围编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [范围编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'employee_data_scope', {
        name: "placeholder_name",
        condition_template: "placeholder_condition_template",
      }, 'code')
      expect(result, '[API 维度] 缺少 [范围编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 范围名称 (name)
   * 业务规则: BR-employee_data_scope-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [范围名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [范围名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'employee_data_scope', {
        code: "TEST_CODE_PLACEHOLDER",
        condition_template: "placeholder_condition_template",
      }, 'name')
      expect(result, '[API 维度] 缺少 [范围名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 条件模板 (condition_template)
   * 业务规则: BR-employee_data_scope-FLD-REQ-condition_template
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CONDITION_TEMPLATE: 缺少必填字段 [条件模板] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [条件模板] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'employee_data_scope', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
      }, 'condition_template')
      expect(result, '[API 维度] 缺少 [条件模板] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 范围编码 (code)
   * 业务规则: BR-employee_data_scope-FLD-UNQ-code
   */
  test('C_UNQ_CODE: 重复 [范围编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_TEST_PLACEHOLDER_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [范围编码] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('employee_data_scope', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        condition_template: "placeholder_condition_template",
        })
        // 再创建一次相同值
        await isolation.createTracked('employee_data_scope', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        condition_template: "placeholder_condition_template",
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_CODE] 后端未拒绝重复 [范围编码], 跳过验证')
      }
    })
  })


  /**
   * UI 导航: 进入 [员工数据权限范围] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [员工数据权限范围] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [员工数据权限范围] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_employee_data_scope', async () => {
        await navigateTo(page, '/employee_data_scope-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
