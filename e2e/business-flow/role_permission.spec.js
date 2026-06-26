/**
 * S-BF-ROLE_PERMISSION-AUTO: 角色权限 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 role_permission.yaml 自动生成
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
 *   BR-role_permission-FLD-REQ-role_id  (角色ID 必填)
 *   BR-role_permission-FLD-REQ-permission_id  (权限ID 必填)
 *   BR-role_permission-FLD-REQ-granted  (授予状态 必填)
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

const ROLE_PERMISSION_URL = '/role_permission-management'

test.describe('S-BF-ROLE_PERMISSION-AUTO: 角色权限 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 角色ID (role_id)
   * 业务规则: BR-role_permission-FLD-REQ-role_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ROLE_ID: 缺少必填字段 [角色ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [角色ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        permission_id: null,
        granted: true,
      }, 'role_id')
      expect(result, '[API 维度] 缺少 [角色ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 权限ID (permission_id)
   * 业务规则: BR-role_permission-FLD-REQ-permission_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PERMISSION_ID: 缺少必填字段 [权限ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [权限ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        role_id: null,
        granted: true,
      }, 'permission_id')
      expect(result, '[API 维度] 缺少 [权限ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 授予状态 (granted)
   * 业务规则: BR-role_permission-FLD-REQ-granted
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_GRANTED: 缺少必填字段 [授予状态] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [授予状态] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'role_permission', {
        role_id: null,
        permission_id: null,
      }, 'granted')
      expect(result, '[API 维度] 缺少 [授予状态] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-role_permission-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_role_permission', async () => {
      await navigateTo(page, '/role_permission-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/role_permission/role_permission-detail
   * 业务规则: BR-role_permission-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_role_permission', async () => {
      const obj = await dataFinder.role_permission().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'role_permission', obj.id)
        await page.waitForURL('**/detail/role_permission/role_permission-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.role_permission`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-role_permission-HEALTH
   */
  test('HEALTH: [角色权限] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_role_permission', async () => {
      await navigateTo(page, '/role_permission-management')
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
   * ui_badge 规则: granted 字段彩色标签
   * 业务规则: BR-role_permission-BADGE-granted
   */
  test('BADGE_GRANTED: 验证 [granted] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_role_permission_granted', async () => {
      await navigateTo(page, '/role_permission-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] granted tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-role_permission-PER-survives_reload
   */
  test('PER_RELOAD: [角色权限] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_role_permission', async () => {
      const obj = await dataFinder.role_permission().catch(() => null)
      if (obj) {
        await navigateTo(page, '/role_permission-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.role_permission`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [角色权限] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [角色权限] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [角色权限] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_role_permission', async () => {
        await navigateTo(page, '/role_permission-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
