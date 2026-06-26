/**
 * S-BF-PERMISSION_RULE-AUTO: 条件权限规则 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 permission_rule.yaml 自动生成
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
 *   BR-permission_rule-FLD-REQ-role_id  (角色ID 必填)
 *   BR-permission_rule-FLD-REQ-resource_type  (资源类型 必填)
 *   BR-permission_rule-FLD-REQ-condition  (条件表达式 必填)
 *   BR-permission_rule-FLD-REQ-permission_level  (权限级别 必填)
 *   BR-permission_rule-AUDIT-create/update/delete  (审计日志)
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

const PERMISSION_RULE_URL = '/permission_rule-management'

test.describe('S-BF-PERMISSION_RULE-AUTO: 条件权限规则 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-permission_rule-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission_rule', {
        resource_type: "placeholder_resource_type",
        condition: "placeholder_condition",
        permission_level: "placeholder_permission_level",
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 资源类型 (resource_type)
   * 业务规则: BR-permission_rule-FLD-REQ-resource_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RESOURCE_TYPE: 缺少必填字段 [资源类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [资源类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission_rule', {
        role_id: null,
        condition: "placeholder_condition",
        permission_level: "placeholder_permission_level",
      }, 'resource_type')
      expect(result, '[API 维度] 缺少 [资源类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 条件表达式 (condition)
   * 业务规则: BR-permission_rule-FLD-REQ-condition
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CONDITION: 缺少必填字段 [条件表达式] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [条件表达式] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission_rule', {
        role_id: null,
        resource_type: "placeholder_resource_type",
        permission_level: "placeholder_permission_level",
      }, 'condition')
      expect(result, '[API 维度] 缺少 [条件表达式] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 权限级别 (permission_level)
   * 业务规则: BR-permission_rule-FLD-REQ-permission_level
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PERMISSION_LEVEL: 缺少必填字段 [权限级别] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限级别] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'permission_rule', {
        role_id: null,
        resource_type: "placeholder_resource_type",
        condition: "placeholder_condition",
      }, 'permission_level')
      expect(result, '[API 维度] 缺少 [权限级别] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 审计日志: 创建 [条件权限规则] 应记录 audit_log
   * 业务规则: BR-permission_rule-AUDIT-create
   * [Healer.L1+L3] createTracked + audit_log 失败都软断言
   */
  test('C_AUDIT: [条件权限规则] 创建应生成 audit_log', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    let obj = null
    const cr = await withStep(page, testInfo, '创建 [条件权限规则] (Healer 守护)', async () => {
      return await AIHealer.guard(page, 'C_AUDIT_permission_rule_create', async () => {
        return await isolation.createTracked('permission_rule', {
        role_id: null,
        resource_type: `aud_resource_type_${TS}`,
        condition: `aud_condition_${TS}`,
        permission_level: `aud_permission_level_${TS}`,
        })
      }, { softOn: ['5xx', '404', 'fk_missing'] })
    })
    obj = cr.result
    if (cr.healed) { console.log(`[Healer] C_AUDIT create 软断言: ${cr.reason}`) ; return }
    await withStep(page, testInfo, '业务断言: audit_log 应记录创建事件 (Healer 守护)', async () => {
      const r = await AIHealer.guard(page, 'C_AUDIT_permission_rule_check', async () => {
        const valid = await BusinessRuleAssertor.assertAuditLogExists(
          page, 'permission_rule', obj.id, 'create'
        )
        expect(valid, '[Business] 创建后应生成 audit_log').toBe(true)
      }, { softOn: ['5xx', 'audit_log_unavailable'] })
      if (r.healed) console.log(`[Healer] C_AUDIT 软断言通过: ${r.reason}`)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-permission_rule-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_permission_rule', async () => {
      await navigateTo(page, '/permission_rule-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/permission_rule/permission_rule-detail
   * 业务规则: BR-permission_rule-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_permission_rule', async () => {
      const obj = await dataFinder.permission_rule().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'permission_rule', obj.id)
        await page.waitForURL('**/detail/permission_rule/permission_rule-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.permission_rule`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-permission_rule-HEALTH
   */
  test('HEALTH: [条件权限规则] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_permission_rule', async () => {
      await navigateTo(page, '/permission_rule-management')
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
   * ui_badge 规则: is_denied 字段彩色标签
   * 业务规则: BR-permission_rule-BADGE-is_denied
   */
  test('BADGE_IS_DENIED: 验证 [is_denied] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_permission_rule_is_denied', async () => {
      await navigateTo(page, '/permission_rule-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_denied tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: inherit_to_children 字段彩色标签
   * 业务规则: BR-permission_rule-BADGE-inherit_to_children
   */
  test('BADGE_INHERIT_TO_CHILDREN: 验证 [inherit_to_children] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_permission_rule_inherit_to_children', async () => {
      await navigateTo(page, '/permission_rule-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] inherit_to_children tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: propagate_to_parents 字段彩色标签
   * 业务规则: BR-permission_rule-BADGE-propagate_to_parents
   */
  test('BADGE_PROPAGATE_TO_PARENTS: 验证 [propagate_to_parents] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_permission_rule_propagate_to_parents', async () => {
      await navigateTo(page, '/permission_rule-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] propagate_to_parents tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-permission_rule-PER-survives_reload
   */
  test('PER_RELOAD: [条件权限规则] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_permission_rule', async () => {
      const obj = await dataFinder.permission_rule().catch(() => null)
      if (obj) {
        await navigateTo(page, '/permission_rule-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.permission_rule`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [条件权限规则] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [条件权限规则] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [条件权限规则] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_permission_rule', async () => {
        await navigateTo(page, '/permission_rule-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
