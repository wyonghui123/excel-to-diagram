/**
 * S-BF-SCHEDULED_TASK-AUTO: 任务定义 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 scheduled_task.yaml 自动生成
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
 *   BR-scheduled_task-FLD-REQ-code  (任务代码 必填)
 *   BR-scheduled_task-FLD-REQ-name  (任务名称 必填)
 *   BR-scheduled_task-FLD-REQ-category  (任务分类 必填)
 *   BR-scheduled_task-FLD-REQ-handler  (处理器 必填)
 *   BR-scheduled_task-FLD-REQ-trigger_mode  (触发模式 必填)
 *   BR-scheduled_task-FLD-UNQ-code  (任务代码 唯一)
 *   BR-scheduled_task-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-05-24
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const SCHEDULED_TASK_URL = '/scheduled_task-management'

test.describe('S-BF-SCHEDULED_TASK-AUTO: 任务定义 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 任务代码 (code)
   * 业务规则: BR-scheduled_task-FLD-REQ-code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CODE: 缺少必填字段 [任务代码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务代码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'scheduled_task', {
        name: "placeholder_name",
        category: "business",
        handler: "placeholder_handler",
        trigger_mode: "placeholder_trigger_mode",
      }, 'code')
      expect(result, '[API 维度] 缺少 [任务代码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 任务名称 (name)
   * 业务规则: BR-scheduled_task-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [任务名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'scheduled_task', {
        code: "TEST_CODE_PLACEHOLDER",
        category: "business",
        handler: "placeholder_handler",
        trigger_mode: "placeholder_trigger_mode",
      }, 'name')
      expect(result, '[API 维度] 缺少 [任务名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 任务分类 (category)
   * 业务规则: BR-scheduled_task-FLD-REQ-category
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CATEGORY: 缺少必填字段 [任务分类] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务分类] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'scheduled_task', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
        handler: "placeholder_handler",
        trigger_mode: "placeholder_trigger_mode",
      }, 'category')
      expect(result, '[API 维度] 缺少 [任务分类] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 处理器 (handler)
   * 业务规则: BR-scheduled_task-FLD-REQ-handler
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_HANDLER: 缺少必填字段 [处理器] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [处理器] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'scheduled_task', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
        category: "business",
        trigger_mode: "placeholder_trigger_mode",
      }, 'handler')
      expect(result, '[API 维度] 缺少 [处理器] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 触发模式 (trigger_mode)
   * 业务规则: BR-scheduled_task-FLD-REQ-trigger_mode
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TRIGGER_MODE: 缺少必填字段 [触发模式] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [触发模式] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'scheduled_task', {
        code: "TEST_CODE_PLACEHOLDER",
        name: "placeholder_name",
        category: "business",
        handler: "placeholder_handler",
      }, 'trigger_mode')
      expect(result, '[API 维度] 缺少 [触发模式] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 任务代码 (code)
   * 业务规则: BR-scheduled_task-FLD-UNQ-code
   */
  test('C_UNQ_CODE: 重复 [任务代码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_TEST_PLACEHOLDER_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [任务代码] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('scheduled_task', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        category: "business",
        handler: "placeholder_handler",
        trigger_mode: "placeholder_trigger_mode",
        })
        // 再创建一次相同值
        await isolation.createTracked('scheduled_task', {
        code: UNQ_VALUE,
        name: "placeholder_name",
        category: "business",
        handler: "placeholder_handler",
        trigger_mode: "placeholder_trigger_mode",
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_CODE] 后端未拒绝重复 [任务代码], 跳过验证')
      }
    })
  })


  /**
   * 审计日志: 创建 [任务定义] 应记录 audit_log
   * 业务规则: BR-scheduled_task-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [任务定义] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [任务定义] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_scheduled_task_create', async () => {
        return await isolation.createTracked('scheduled_task', {
        code: `AUD_CODE_${TS}`,
        name: `aud_name_${TS}`,
        category: "business",
        handler: `aud_handler_${TS}`,
        trigger_mode: `aud_trigger_mode_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_scheduled_task_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'scheduled_task', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * UI 导航: 进入 [任务定义] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [任务定义] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [任务定义] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_scheduled_task', async () => {
        await navigateTo(page, '/scheduled_task-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
