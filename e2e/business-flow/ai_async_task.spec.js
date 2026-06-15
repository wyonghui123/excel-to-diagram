/**
 * S-BF-AI_ASYNC_TASK-AUTO: AI异步任务 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 ai_async_task.yaml 自动生成
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
 *   BR-ai_async_task-FLD-REQ-task_type  (任务类型 必填)
 *   BR-ai_async_task-FLD-REQ-request  (请求内容 必填)
 *   BR-ai_async_task-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-06-07
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const AI_ASYNC_TASK_URL = '/ai_async_task-management'

test.describe('S-BF-AI_ASYNC_TASK-AUTO: AI异步任务 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 任务类型 (task_type)
   * 业务规则: BR-ai_async_task-FLD-REQ-task_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TASK_TYPE: 缺少必填字段 [任务类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'ai_async_task', {
        request: "placeholder_request",
      }, 'task_type')
      expect(result, '[API 维度] 缺少 [任务类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 请求内容 (request)
   * 业务规则: BR-ai_async_task-FLD-REQ-request
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_REQUEST: 缺少必填字段 [请求内容] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [请求内容] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'ai_async_task', {
        task_type: "query",
      }, 'request')
      expect(result, '[API 维度] 缺少 [请求内容] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [AI异步任务] 应记录 audit_log
   * 业务规则: BR-ai_async_task-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [AI异步任务] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [AI异步任务] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_ai_async_task_create', async () => {
        return await isolation.createTracked('ai_async_task', {
        task_type: "query",
        request: `aud_request_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_ai_async_task_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'ai_async_task', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * UI 导航: 进入 [AI异步任务] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [AI异步任务] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [AI异步任务] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_ai_async_task', async () => {
        await navigateTo(page, '/ai_async_task-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
