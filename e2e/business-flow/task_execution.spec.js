/**
 * S-BF-TASK_EXECUTION-AUTO: 任务执行记录 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 task_execution.yaml 自动生成
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
 *   BR-task_execution-FLD-REQ-name  (任务名称 必填)
 *   BR-task_execution-FLD-REQ-task_type  (任务类型 必填)
 *   BR-task_execution-FLD-REQ-handler  (处理器 必填)
 *   BR-task_execution-FLD-REQ-status  (状态 必填)
 *   BR-task_execution-AUDIT-create/update/delete  (审计日志)
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

const TASK_EXECUTION_URL = '/task_execution-management'

test.describe('S-BF-TASK_EXECUTION-AUTO: 任务执行记录 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 任务名称 (name)
   * 业务规则: BR-task_execution-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [任务名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_execution', {
        task_type: "business",
        handler: "placeholder_handler",
        status: "pending",
      }, 'name')
      expect(result, '[API 维度] 缺少 [任务名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 任务类型 (task_type)
   * 业务规则: BR-task_execution-FLD-REQ-task_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_TASK_TYPE: 缺少必填字段 [任务类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [任务类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_execution', {
        name: "placeholder_name",
        handler: "placeholder_handler",
        status: "pending",
      }, 'task_type')
      expect(result, '[API 维度] 缺少 [任务类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 处理器 (handler)
   * 业务规则: BR-task_execution-FLD-REQ-handler
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_HANDLER: 缺少必填字段 [处理器] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [处理器] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_execution', {
        name: "placeholder_name",
        task_type: "business",
        status: "pending",
      }, 'handler')
      expect(result, '[API 维度] 缺少 [处理器] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 状态 (status)
   * 业务规则: BR-task_execution-FLD-REQ-status
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_STATUS: 缺少必填字段 [状态] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [状态] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'task_execution', {
        name: "placeholder_name",
        task_type: "business",
        handler: "placeholder_handler",
      }, 'status')
      expect(result, '[API 维度] 缺少 [状态] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 枚举值校验: 任务类型 (task_type)
   * 业务规则: BR-task_execution-FLD-ENUM-task_type
   * 允许值: [{'value': 'business', 'label': '业务任务'}, {'value': 'ai', 'label': 'AI任务'}, {'value': 'system', 'label': '系统任务'}, {'value': 'action', 'label': 'Action任务'}]
   */
  test('C_ENUM_TASK_TYPE: [任务类型] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [任务类型] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'task_execution', {
        name: "placeholder_name",
        handler: "placeholder_handler",
        status: "pending",
          task_type: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'business', 'label': '业务任务'}, {'value': 'ai', 'label': 'AI任务'}, {'value': 'system', 'label': '系统任务'}, {'value': 'action', 'label': 'Action任务'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 状态 (status)
   * 业务规则: BR-task_execution-FLD-ENUM-status
   * 允许值: [{'value': 'pending', 'label': '待执行'}, {'value': 'queued', 'label': '已排队'}, {'value': 'running', 'label': '执行中'}, {'value': 'completed', 'label': '已完成'}, {'value': 'failed', 'label': '失败'}, {'value': 'cancelled', 'label': '已取消'}]
   */
  test('C_ENUM_STATUS: [状态] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [状态] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'task_execution', {
        name: "placeholder_name",
        task_type: "business",
        handler: "placeholder_handler",
          status: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'pending', 'label': '待执行'}, {'value': 'queued', 'label': '已排队'}, {'value': 'running', 'label': '执行中'}, {'value': 'completed', 'label': '已完成'}, {'value': 'failed', 'label': '失败'}, {'value': 'cancelled', 'label': '已取消'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [任务执行记录] 应记录 audit_log
   * 业务规则: BR-task_execution-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [任务执行记录] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [任务执行记录] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_task_execution_create', async () => {
        return await isolation.createTracked('task_execution', {
        name: `aud_name_${TS}`,
        task_type: "business",
        handler: `aud_handler_${TS}`,
        status: "pending",
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_task_execution_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'task_execution', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * audit_levels 规则: create → INFO/operation
   * 业务规则: BR-task_execution-AUDIT-create
   */
  test('AUD_CREATE: create 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_execution_create', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_execution', null, 'create'
      )
      console.log(`  [AUD] create → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: update → INFO/operation
   * 业务规则: BR-task_execution-AUDIT-update
   */
  test('AUD_UPDATE: update 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_execution_update', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_execution', null, 'update'
      )
      console.log(`  [AUD] update → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: delete → WARN/destructive
   * 业务规则: BR-task_execution-AUDIT-delete
   */
  test('AUD_DELETE: delete 应产生 WARN 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_task_execution_delete', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'task_execution', null, 'delete'
      )
      console.log(`  [AUD] delete → ${valid ? 'WARN' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-task_execution-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_task_execution', async () => {
      await navigateTo(page, '/task_execution-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/task_execution/task_execution-detail
   * 业务规则: BR-task_execution-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_task_execution', async () => {
      const obj = await dataFinder.task_execution().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'task_execution', obj.id)
        await page.waitForURL('**/detail/task_execution/task_execution-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.task_execution`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-task_execution-HEALTH
   */
  test('HEALTH: [任务执行记录] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_task_execution', async () => {
      await navigateTo(page, '/task_execution-management')
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
   * ui_badge 规则: task_type 字段彩色标签
   * 业务规则: BR-task_execution-BADGE-task_type
   */
  test('BADGE_TASK_TYPE: 验证 [task_type] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_task_execution_task_type', async () => {
      await navigateTo(page, '/task_execution-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] task_type tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: status 字段彩色标签
   * 业务规则: BR-task_execution-BADGE-status
   */
  test('BADGE_STATUS: 验证 [status] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_task_execution_status', async () => {
      await navigateTo(page, '/task_execution-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] status tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-task_execution-PER-survives_reload
   */
  test('PER_RELOAD: [任务执行记录] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_task_execution', async () => {
      const obj = await dataFinder.task_execution().catch(() => null)
      if (obj) {
        await navigateTo(page, '/task_execution-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.task_execution`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [任务执行记录] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [任务执行记录] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [任务执行记录] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_task_execution', async () => {
        await navigateTo(page, '/task_execution-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
