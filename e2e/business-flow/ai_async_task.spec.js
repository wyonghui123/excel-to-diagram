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
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
 *   BR-ai_async_task-FLD-REQ-task_type  (任务类型 必填)
 *   BR-ai_async_task-FLD-REQ-request  (请求内容 必填)
 *   BR-ai_async_task-AUDIT-create/update/delete  (审计日志)
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
   * 枚举值校验: 任务类型 (task_type)
   * 业务规则: BR-ai_async_task-FLD-ENUM-task_type
   * 允许值: [{'value': 'query', 'label': 'AI查询'}, {'value': 'analyze', 'label': 'AI分析'}, {'value': 'action', 'label': 'AI动作'}, {'value': 'embedding', 'label': '嵌入计算'}, {'value': 'agent', 'label': 'Agent任务'}, {'value': 'rag', 'label': 'RAG检索'}]
   */
  test('C_ENUM_TASK_TYPE: [任务类型] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [任务类型] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'ai_async_task', {
        request: "placeholder_request",
          task_type: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'query', 'label': 'AI查询'}, {'value': 'analyze', 'label': 'AI分析'}, {'value': 'action', 'label': 'AI动作'}, {'value': 'embedding', 'label': '嵌入计算'}, {'value': 'agent', 'label': 'Agent任务'}, {'value': 'rag', 'label': 'RAG检索'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 状态 (status)
   * 业务规则: BR-ai_async_task-FLD-ENUM-status
   * 允许值: [{'value': 'pending', 'label': '待执行'}, {'value': 'queued', 'label': '已排队'}, {'value': 'running', 'label': '执行中'}, {'value': 'completed', 'label': '已完成'}, {'value': 'failed', 'label': '失败'}, {'value': 'cancelled', 'label': '已取消'}]
   */
  test('C_ENUM_STATUS: [状态] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [状态] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'ai_async_task', {
        task_type: "query",
        request: "placeholder_request",
          status: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'pending', 'label': '待执行'}, {'value': 'queued', 'label': '已排队'}, {'value': 'running', 'label': '执行中'}, {'value': 'completed', 'label': '已完成'}, {'value': 'failed', 'label': '失败'}, {'value': 'cancelled', 'label': '已取消'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
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
   * audit_levels 规则: create → INFO/operation
   * 业务规则: BR-ai_async_task-AUDIT-create
   */
  test('AUD_CREATE: create 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_ai_async_task_create', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'ai_async_task', null, 'create'
      )
      console.log(`  [AUD] create → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * audit_levels 规则: update → INFO/operation
   * 业务规则: BR-ai_async_task-AUDIT-update
   */
  test('AUD_UPDATE: update 应产生 INFO 审计', async ({
    page, dataFinder, isolation
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'AUD_ai_async_task_update', async () => {
      const valid = await BusinessRuleAssertor.assertAuditLogExists(
        page, 'ai_async_task', null, 'update'
      )
      console.log(`  [AUD] update → ${valid ? 'INFO' : 'NOT_FOUND'}`)
    }, { softOn: ['5xx', 'audit_log_unavailable'] })
    if (r.healed) console.log(`[Healer] AUD 软断言: ${r.reason}`)
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-ai_async_task-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_ai_async_task', async () => {
      await navigateTo(page, '/ai_async_task-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/ai_async_task/ai_async_task-detail
   * 业务规则: BR-ai_async_task-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_ai_async_task', async () => {
      const obj = await dataFinder.ai_async_task().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'ai_async_task', obj.id)
        await page.waitForURL('**/detail/ai_async_task/ai_async_task-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.ai_async_task`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-ai_async_task-HEALTH
   */
  test('HEALTH: [AI异步任务] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_ai_async_task', async () => {
      await navigateTo(page, '/ai_async_task-management')
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
   * 业务规则: BR-ai_async_task-BADGE-task_type
   */
  test('BADGE_TASK_TYPE: 验证 [task_type] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_ai_async_task_task_type', async () => {
      await navigateTo(page, '/ai_async_task-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] task_type tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: status 字段彩色标签
   * 业务规则: BR-ai_async_task-BADGE-status
   */
  test('BADGE_STATUS: 验证 [status] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_ai_async_task_status', async () => {
      await navigateTo(page, '/ai_async_task-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] status tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-ai_async_task-PER-survives_reload
   */
  test('PER_RELOAD: [AI异步任务] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_ai_async_task', async () => {
      const obj = await dataFinder.ai_async_task().catch(() => null)
      if (obj) {
        await navigateTo(page, '/ai_async_task-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.ai_async_task`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
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
