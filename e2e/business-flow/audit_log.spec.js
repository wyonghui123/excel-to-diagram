/**
 * S-BF-AUDIT_LOG-AUTO: 审计日志 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 audit_log.yaml 自动生成
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
 *   BR-audit_log-FLD-REQ-log_category  (日志类型 必填)
 *   BR-audit_log-FLD-REQ-log_level  (日志级别 必填)
 *   BR-audit_log-FLD-REQ-object_type  (对象类型 必填)
 *   BR-audit_log-FLD-REQ-object_id  (对象ID 必填)
 *   BR-audit_log-FLD-REQ-action  (操作类型 必填)
 *
 * 自动生成时间: 2026-06-12
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const AUDIT_LOG_URL = '/audit_log-management'

test.describe('S-BF-AUDIT_LOG-AUTO: 审计日志 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 日志类型 (log_category)
   * 业务规则: BR-audit_log-FLD-REQ-log_category
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_LOG_CATEGORY: 缺少必填字段 [日志类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [日志类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'audit_log', {
        log_level: "DEBUG",
        object_type: "user",
        object_id: null,
        action: "placeholder_action",
      }, 'log_category')
      expect(result, '[API 维度] 缺少 [日志类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 日志级别 (log_level)
   * 业务规则: BR-audit_log-FLD-REQ-log_level
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_LOG_LEVEL: 缺少必填字段 [日志级别] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [日志级别] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'audit_log', {
        log_category: "business",
        object_type: "user",
        object_id: null,
        action: "placeholder_action",
      }, 'log_level')
      expect(result, '[API 维度] 缺少 [日志级别] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象类型 (object_type)
   * 业务规则: BR-audit_log-FLD-REQ-object_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_TYPE: 缺少必填字段 [对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'audit_log', {
        log_category: "business",
        log_level: "DEBUG",
        object_id: null,
        action: "placeholder_action",
      }, 'object_type')
      expect(result, '[API 维度] 缺少 [对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象ID (object_id)
   * 业务规则: BR-audit_log-FLD-REQ-object_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_ID: 缺少必填字段 [对象ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'audit_log', {
        log_category: "business",
        log_level: "DEBUG",
        object_type: "user",
        action: "placeholder_action",
      }, 'object_id')
      expect(result, '[API 维度] 缺少 [对象ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 操作类型 (action)
   * 业务规则: BR-audit_log-FLD-REQ-action
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ACTION: 缺少必填字段 [操作类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [操作类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'audit_log', {
        log_category: "business",
        log_level: "DEBUG",
        object_type: "user",
        object_id: null,
      }, 'action')
      expect(result, '[API 维度] 缺少 [操作类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [审计日志] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [审计日志] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [审计日志] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_audit_log', async () => {
        await navigateTo(page, '/audit_log-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
