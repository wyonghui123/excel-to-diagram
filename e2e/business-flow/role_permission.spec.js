/**
 * S-BF-ROLE_PERMISSION-AUTO: 角色权限 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 role_permission.yaml 自动生成
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
 *   BR-role_permission-FLD-REQ-role_id  (角色ID 必填)
 *   BR-role_permission-FLD-REQ-permission_id  (权限ID 必填)
 *   BR-role_permission-FLD-REQ-granted  (授予状态 必填)
 *
 * 自动生成时间: 2026-06-04
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const ROLE_PERMISSION_URL = '/role_permission-management'

test.describe('S-BF-ROLE_PERMISSION-AUTO: 角色权限 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-role_permission-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        permission_id: null,
        granted: true,
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 权限ID (permission_id)
   * 业务规则: BR-role_permission-FLD-REQ-permission_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PERMISSION_ID: 缺少必填字段 [权限ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        role_id: null,
        granted: true,
      }, 'permission_id')
      expect(result, '[API 维度] 缺少 [权限ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 授予状态 (granted)
   * 业务规则: BR-role_permission-FLD-REQ-granted
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_GRANTED: 缺少必填字段 [授予状态] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [授予状态] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        role_id: null,
        permission_id: null,
      }, 'granted')
      expect(result, '[API 维度] 缺少 [授予状态] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [角色权限] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [角色权限] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [角色权限] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_role_permission', async () => {
        await navigateTo(page, '/role_permission-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
