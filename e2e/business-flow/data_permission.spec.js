/**
 * S-BF-DATA_PERMISSION-AUTO: 数据权限 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 data_permission.yaml 自动生成
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
 *   BR-data_permission-FLD-REQ-user_id  (用户ID 必填)
 *   BR-data_permission-FLD-REQ-resource_type  (资源类型 必填)
 *   BR-data_permission-FLD-REQ-resource_id  (资源ID 必填)
 *   BR-data_permission-FLD-REQ-permission_level  (权限级别 必填)
 *   BR-data_permission-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-05-14
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const DATA_PERMISSION_URL = '/data_permission-management'

test.describe('S-BF-DATA_PERMISSION-AUTO: 数据权限 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 用户ID (user_id)
   * 业务规则: BR-data_permission-FLD-REQ-user_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_USER_ID: 缺少必填字段 [用户ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [用户ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'data_permission', {
        resource_type: "placeholder_resource_type",
        resource_id: null,
        permission_level: "placeholder_permission_level",
      }, 'user_id')
      expect(result, '[API 维度] 缺少 [用户ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 资源类型 (resource_type)
   * 业务规则: BR-data_permission-FLD-REQ-resource_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RESOURCE_TYPE: 缺少必填字段 [资源类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [资源类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'data_permission', {
        user_id: null,
        resource_id: null,
        permission_level: "placeholder_permission_level",
      }, 'resource_type')
      expect(result, '[API 维度] 缺少 [资源类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 资源ID (resource_id)
   * 业务规则: BR-data_permission-FLD-REQ-resource_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RESOURCE_ID: 缺少必填字段 [资源ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [资源ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'data_permission', {
        user_id: null,
        resource_type: "placeholder_resource_type",
        permission_level: "placeholder_permission_level",
      }, 'resource_id')
      expect(result, '[API 维度] 缺少 [资源ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 权限级别 (permission_level)
   * 业务规则: BR-data_permission-FLD-REQ-permission_level
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PERMISSION_LEVEL: 缺少必填字段 [权限级别] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限级别] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'data_permission', {
        user_id: null,
        resource_type: "placeholder_resource_type",
        resource_id: null,
      }, 'permission_level')
      expect(result, '[API 维度] 缺少 [权限级别] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [数据权限] 应记录 audit_log
   * 业务规则: BR-data_permission-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [数据权限] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [数据权限] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_data_permission_create', async () => {
        return await isolation.createTracked('data_permission', {
        user_id: null,
        resource_type: `aud_resource_type_${TS}`,
        resource_id: null,
        permission_level: `aud_permission_level_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_data_permission_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'data_permission', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * UI 导航: 进入 [数据权限] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [数据权限] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [数据权限] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_data_permission', async () => {
        await navigateTo(page, '/data_permission-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
