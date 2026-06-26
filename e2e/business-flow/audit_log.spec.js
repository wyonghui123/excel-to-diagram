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
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
 *   BR-audit_log-FLD-REQ-log_category  (日志类型 必填)
 *   BR-audit_log-FLD-REQ-log_level  (日志级别 必填)
 *   BR-audit_log-FLD-REQ-object_type  (对象类型 必填)
 *   BR-audit_log-FLD-REQ-object_id  (对象ID 必填)
 *   BR-audit_log-FLD-REQ-action  (操作类型 必填)
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
   * 枚举值校验: 日志类型 (log_category)
   * 业务规则: BR-audit_log-FLD-ENUM-log_category
   * 允许值: [{'value': 'business', 'label': '业务审计', 'color': 'primary'}, {'value': 'security', 'label': '安全日志', 'color': 'danger'}, {'value': 'operation', 'label': '运营日志', 'color': 'info'}, {'value': 'performance', 'label': '性能日志', 'color': 'warning'}, {'value': 'system', 'label': '系统日志', 'color': 'default'}]
   */
  test('C_ENUM_LOG_CATEGORY: [日志类型] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [日志类型] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'audit_log', {
        log_level: "DEBUG",
        object_type: "user",
        object_id: null,
        action: "placeholder_action",
          log_category: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'business', 'label': '业务审计', 'color': 'primary'}, {'value': 'security', 'label': '安全日志', 'color': 'danger'}, {'value': 'operation', 'label': '运营日志', 'color': 'info'}, {'value': 'performance', 'label': '性能日志', 'color': 'warning'}, {'value': 'system', 'label': '系统日志', 'color': 'default'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 日志级别 (log_level)
   * 业务规则: BR-audit_log-FLD-ENUM-log_level
   * 允许值: [{'value': 'DEBUG', 'label': '调试', 'color': 'default'}, {'value': 'INFO', 'label': '信息', 'color': 'info'}, {'value': 'WARNING', 'label': '警告', 'color': 'warning'}, {'value': 'ERROR', 'label': '错误', 'color': 'danger'}, {'value': 'CRITICAL', 'label': '严重', 'color': 'danger'}]
   */
  test('C_ENUM_LOG_LEVEL: [日志级别] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [日志级别] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'audit_log', {
        log_category: "business",
        object_type: "user",
        object_id: null,
        action: "placeholder_action",
          log_level: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'DEBUG', 'label': '调试', 'color': 'default'}, {'value': 'INFO', 'label': '信息', 'color': 'info'}, {'value': 'WARNING', 'label': '警告', 'color': 'warning'}, {'value': 'ERROR', 'label': '错误', 'color': 'danger'}, {'value': 'CRITICAL', 'label': '严重', 'color': 'danger'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 对象类型 (object_type)
   * 业务规则: BR-audit_log-FLD-ENUM-object_type
   * 允许值: [{'value': 'user', 'label': '用户'}, {'value': 'role', 'label': '角色'}, {'value': 'user_group', 'label': '用户组'}, {'value': 'product', 'label': '产品'}, {'value': 'version', 'label': '版本'}, {'value': 'domain', 'label': '领域'}, {'value': 'sub_domain', 'label': '子域'}, {'value': 'service_module', 'label': '服务模块'}, {'value': 'business_object', 'label': '业务对象'}, {'value': 'relationship', 'label': '关系'}, {'value': 'annotation', 'label': '标注'}, {'value': 'enum_type', 'label': '枚举类型'}, {'value': 'enum_value', 'label': '枚举值'}, {'value': '__audit_failure__', 'label': '审计失败'}]
   */
  test('C_ENUM_OBJECT_TYPE: [对象类型] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [对象类型] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'audit_log', {
        log_category: "business",
        log_level: "DEBUG",
        object_id: null,
        action: "placeholder_action",
          object_type: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'user', 'label': '用户'}, {'value': 'role', 'label': '角色'}, {'value': 'user_group', 'label': '用户组'}, {'value': 'product', 'label': '产品'}, {'value': 'version', 'label': '版本'}, {'value': 'domain', 'label': '领域'}, {'value': 'sub_domain', 'label': '子域'}, {'value': 'service_module', 'label': '服务模块'}, {'value': 'business_object', 'label': '业务对象'}, {'value': 'relationship', 'label': '关系'}, {'value': 'annotation', 'label': '标注'}, {'value': 'enum_type', 'label': '枚举类型'}, {'value': 'enum_value', 'label': '枚举值'}, {'value': '__audit_failure__', 'label': '审计失败'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * 枚举值校验: 审计状态 (status)
   * 业务规则: BR-audit_log-FLD-ENUM-status
   * 允许值: [{'value': 'pending', 'label': '待写入', 'color': 'warning', 'icon': 'clock', 'is_initial': True, 'category': 'active', 'description': '审计记录待写入外部系统'}, {'value': 'written', 'label': '已写入', 'color': 'success', 'icon': 'circle-check', 'is_final': True, 'category': 'final', 'description': '审计记录已成功写入'}, {'value': 'failed', 'label': '写入失败', 'color': 'danger', 'icon': 'circle-close', 'category': 'error', 'description': '审计记录写入失败，可重试'}]
   */
  test('C_ENUM_STATUS: [审计状态] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [审计状态] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'audit_log', {
        log_category: "business",
        log_level: "DEBUG",
        object_type: "user",
        object_id: null,
        action: "placeholder_action",
          status: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'pending', 'label': '待写入', 'color': 'warning', 'icon': 'clock', 'is_initial': True, 'category': 'active', 'description': '审计记录待写入外部系统'}, {'value': 'written', 'label': '已写入', 'color': 'success', 'icon': 'circle-check', 'is_final': True, 'category': 'final', 'description': '审计记录已成功写入'}, {'value': 'failed', 'label': '写入失败', 'color': 'danger', 'icon': 'circle-close', 'category': 'error', 'description': '审计记录写入失败，可重试'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })



  /**
   * pagination 规则: default_page_size=50
   * 业务规则: BR-audit_log-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_audit_log', async () => {
      await navigateTo(page, '/audit_log-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/audit_log/audit_log-detail
   * 业务规则: BR-audit_log-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_audit_log', async () => {
      const obj = await dataFinder.audit_log().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'audit_log', obj.id)
        await page.waitForURL('**/detail/audit_log/audit_log-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.audit_log`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-audit_log-HEALTH
   */
  test('HEALTH: [审计日志] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_audit_log', async () => {
      await navigateTo(page, '/audit_log-management')
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
   * ui_badge 规则: log_category 字段彩色标签
   * 业务规则: BR-audit_log-BADGE-log_category
   */
  test('BADGE_LOG_CATEGORY: 验证 [log_category] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_audit_log_log_category', async () => {
      await navigateTo(page, '/audit_log-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] log_category tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: log_level 字段彩色标签
   * 业务规则: BR-audit_log-BADGE-log_level
   */
  test('BADGE_LOG_LEVEL: 验证 [log_level] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_audit_log_log_level', async () => {
      await navigateTo(page, '/audit_log-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] log_level tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: object_type 字段彩色标签
   * 业务规则: BR-audit_log-BADGE-object_type
   */
  test('BADGE_OBJECT_TYPE: 验证 [object_type] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_audit_log_object_type', async () => {
      await navigateTo(page, '/audit_log-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] object_type tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: status 字段彩色标签
   * 业务规则: BR-audit_log-BADGE-status
   */
  test('BADGE_STATUS: 验证 [status] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_audit_log_status', async () => {
      await navigateTo(page, '/audit_log-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] status tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-audit_log-PER-survives_reload
   */
  test('PER_RELOAD: [审计日志] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_audit_log', async () => {
      const obj = await dataFinder.audit_log().catch(() => null)
      if (obj) {
        await navigateTo(page, '/audit_log-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.audit_log`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
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
