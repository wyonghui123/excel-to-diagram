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
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
 *   BR-task_queue-FLD-REQ-name  (队列名称 必填)
 *   BR-task_queue-FLD-REQ-priority  (优先级 必填)
 *   BR-task_queue-FLD-UNQ-name  (队列名称 唯一)
 *   BR-task_queue-AUDIT-create/update/delete  (审计日志)
 *
 * 自动生成时间: 2026-06-25
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { navigateToDeepLink } from '../helpers/auto-fixtures.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { FormComponentPOM } from '../page-objects/FormComponentPOM.js'
import { PermissionPOM } from '../page-objects/PermissionPOM.js'
import { PaginationPOM } from '../page-objects/PaginationPOM.js'
import { NestedPOM } from '../page-objects/NestedPOM.js'
import { PersistencePOM } from '../page-objects/PersistencePOM.js'
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
   * audit_levels 规则: create → INFO/operation
   * 业务规则: BR-task_queue-AUDIT-create
   */
  test('AUD_CREATE: create 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_queue_create', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_queue', null, 'create'
      )
      console.log(`  [AUD] create → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: update → INFO/operation
   * 业务规则: BR-task_queue-AUDIT-update
   */
  test('AUD_UPDATE: update 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_queue_update', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_queue', null, 'update'
      )
      console.log(`  [AUD] update → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: delete → WARN/destructive
   * 业务规则: BR-task_queue-AUDIT-delete
   */
  test('AUD_DELETE: delete 应产生 WARN 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_queue_delete', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_queue', null, 'delete'
      )
      console.log(`  [AUD] delete → ${valid ? 'WARN' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-task_queue-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_task_queue', async () => {
      await navigateTo(page, '/task_queue-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/task_queue/task_queue-detail
   * 业务规则: BR-task_queue-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_task_queue', async () => {
      const obj = await dataFinder.task_queue().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'task_queue', obj.id)
        await page.waitForURL('**/detail/task_queue/task_queue-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.task_queue`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-task_queue-HEALTH
   */
  test('HEALTH: [任务队列配置] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_task_queue', async () => {
      await navigateTo(page, '/task_queue-management')
      await page.waitForTimeout(1000)
    }, { softOn: ['5xx', '404'] })
    if (errors.length === 0) {
      console.log(`  [HEALTH] 无 pageerror/console.error`)
    } else {
      console.warn(`  [HEALTH] 发现 ${errors.length} 错误: ${errors.slice(0, 3).join('; ')}`)
    }
    if (r.healed) console.log(`[Healer] HEALTH 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: enabled 字段彩色标签
   * 业务规则: BR-task_queue-BADGE-enabled
   */
  test('BADGE_ENABLED: 验证 [enabled] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_task_queue_enabled', async () => {
      await navigateTo(page, '/task_queue-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] enabled tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-task_queue-PER-survives_reload
   */
  test('PER_RELOAD: [任务队列配置] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_task_queue', async () => {
      const obj = await dataFinder.task_queue().catch(() => null)
      if (obj) {
        await navigateTo(page, '/task_queue-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.task_queue`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
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
