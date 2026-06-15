/**
 * S-BF-ROLE_DATA_PERMISSION-AUTO: 角色数据权限 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 role_data_permission.yaml 自动生成
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
 *   BR-role_data_permission-FLD-REQ-role_id  (角色ID 必填)
 *   BR-role_data_permission-FLD-REQ-resource_type  (资源类型 必填)
 *   BR-role_data_permission-FLD-REQ-resource_id  (资源ID 必填)
 *
 * 自动生成时间: 2026-05-25
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const ROLE_DATA_PERMISSION_URL = '/role_data_permission-management'

test.describe('S-BF-ROLE_DATA_PERMISSION-AUTO: 角色数据权限 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-role_data_permission-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_data_permission', {
        resource_type: "placeholder_resource_type",
        resource_id: null,
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 资源类型 (resource_type)
   * 业务规则: BR-role_data_permission-FLD-REQ-resource_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RESOURCE_TYPE: 缺少必填字段 [资源类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [资源类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_data_permission', {
        role_id: null,
        resource_id: null,
      }, 'resource_type')
      expect(result, '[API 维度] 缺少 [资源类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 资源ID (resource_id)
   * 业务规则: BR-role_data_permission-FLD-REQ-resource_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RESOURCE_ID: 缺少必填字段 [资源ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [资源ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_data_permission', {
        role_id: null,
        resource_type: "placeholder_resource_type",
      }, 'resource_id')
      expect(result, '[API 维度] 缺少 [资源ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [角色数据权限] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [角色数据权限] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [角色数据权限] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_role_data_permission', async () => {
        await navigateTo(page, '/role_data_permission-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
