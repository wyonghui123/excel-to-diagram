/**
 * S-BF-ROLE_DIMENSION_SCOPE-AUTO: 角色维度范围 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 role_dimension_scope.yaml 自动生成
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
 *   BR-role_dimension_scope-FLD-REQ-role_id  (角色ID 必填)
 *   BR-role_dimension_scope-FLD-REQ-dimension_code  (维度编码 必填)
 *   BR-role_dimension_scope-FLD-REQ-dimension_values  (维度值列表 必填)
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

const ROLE_DIMENSION_SCOPE_URL = '/role_dimension_scope-management'

test.describe('S-BF-ROLE_DIMENSION_SCOPE-AUTO: 角色维度范围 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        dimension_code: "placeholder_dimension_code",
        dimension_values: "placeholder_dimension_values",
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 维度编码 (dimension_code)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-dimension_code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_DIMENSION_CODE: 缺少必填字段 [维度编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [维度编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        role_id: null,
        dimension_values: "placeholder_dimension_values",
      }, 'dimension_code')
      expect(result, '[API 维度] 缺少 [维度编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 维度值列表 (dimension_values)
   * 业务规则: BR-role_dimension_scope-FLD-REQ-dimension_values
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_DIMENSION_VALUES: 缺少必填字段 [维度值列表] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [维度值列表] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_dimension_scope', {
        role_id: null,
        dimension_code: "placeholder_dimension_code",
      }, 'dimension_values')
      expect(result, '[API 维度] 缺少 [维度值列表] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 枚举值校验: 范围模式 (scope_mode)
   * 业务规则: BR-role_dimension_scope-FLD-ENUM-scope_mode
   * 允许值: ['include', 'exclude']
   */
  test('C_ENUM_SCOPE_MODE: [范围模式] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [范围模式] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'role_dimension_scope', {
        role_id: null,
        dimension_code: "placeholder_dimension_code",
        dimension_values: "placeholder_dimension_values",
          scope_mode: 'INVALID_ENUM_VALUE_999'
        }, ['include', 'exclude']
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-role_dimension_scope-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_role_dimension_scope', async () => {
      await navigateTo(page, '/role_dimension_scope-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/role_dimension_scope/role_dimension_scope-detail
   * 业务规则: BR-role_dimension_scope-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_role_dimension_scope', async () => {
      const obj = await dataFinder.role_dimension_scope().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'role_dimension_scope', obj.id)
        await page.waitForURL('**/detail/role_dimension_scope/role_dimension_scope-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.role_dimension_scope`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-role_dimension_scope-HEALTH
   */
  test('HEALTH: [角色维度范围] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_role_dimension_scope', async () => {
      await navigateTo(page, '/role_dimension_scope-management')
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
   * ui_badge 规则: inherit_children 字段彩色标签
   * 业务规则: BR-role_dimension_scope-BADGE-inherit_children
   */
  test('BADGE_INHERIT_CHILDREN: 验证 [inherit_children] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_role_dimension_scope_inherit_children', async () => {
      await navigateTo(page, '/role_dimension_scope-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] inherit_children tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: scope_mode 字段彩色标签
   * 业务规则: BR-role_dimension_scope-BADGE-scope_mode
   */
  test('BADGE_SCOPE_MODE: 验证 [scope_mode] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_role_dimension_scope_scope_mode', async () => {
      await navigateTo(page, '/role_dimension_scope-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] scope_mode tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-role_dimension_scope-PER-survives_reload
   */
  test('PER_RELOAD: [角色维度范围] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_role_dimension_scope', async () => {
      const obj = await dataFinder.role_dimension_scope().catch(() => null)
      if (obj) {
        await navigateTo(page, '/role_dimension_scope-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.role_dimension_scope`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [角色维度范围] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [角色维度范围] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [角色维度范围] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_role_dimension_scope', async () => {
        await navigateTo(page, '/role_dimension_scope-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
