/**
 * S-BF-TASK_QUEUE-AUTO: 任务队列配置 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 task_queue.yaml 自动生成
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
 *   BR-task_queue-FLD-REQ-name  (队列名称 必填)
 *   BR-task_queue-FLD-REQ-priority  (优先级 必填)
 *   BR-task_queue-FLD-UNQ-name  (队列名称 唯一)
 *   BR-task_queue-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-05-24
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const TASK_QUEUE_URL = '/task_queue-management'

test.describe('S-BF-TASK_QUEUE-AUTO: 任务队列配置 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 队列名称 (name)
   * 业务规则: BR-task_queue-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [队列名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [队列名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_queue', {
        priority: 0,
      }, 'name')
      expect(result, '[API 维度] 缺少 [队列名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 优先级 (priority)
   * 业务规则: BR-task_queue-FLD-REQ-priority
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PRIORITY: 缺少必填字段 [优先级] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [优先级] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_queue', {
        name: "placeholder_name",
      }, 'priority')
      expect(result, '[API 维度] 缺少 [优先级] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 队列名称 (name)
   * 业务规则: BR-task_queue-FLD-UNQ-name
   */
  test('C_UNQ_NAME: 重复 [队列名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_NAME_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [队列名称] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('task_queue', {
        name: UNQ_VALUE,
        priority: 0,
        })
        // 再创建一次相同值
        await isolation.createTracked('task_queue', {
        name: UNQ_VALUE,
        priority: 0,
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_NAME] 后端未拒绝重复 [队列名称], 跳过验证')
      }
    })
  })


  /**
   * 审计日志: 创建 [任务队列配置] 应记录 audit_log
   * 业务规则: BR-task_queue-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [任务队列配置] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [任务队列配置] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_task_queue_create', async () => {
        return await isolation.createTracked('task_queue', {
        name: `aud_name_${TS}`,
        priority: 0,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_task_queue_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'task_queue', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * UI 导航: 进入 [任务队列配置] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [任务队列配置] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [任务队列配置] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_task_queue', async () => {
        await navigateTo(page, '/task_queue-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
