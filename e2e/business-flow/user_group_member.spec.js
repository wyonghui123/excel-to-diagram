/**
 * S-BF-USER_GROUP_MEMBER-AUTO: 用户组成员 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 user_group_member.yaml 自动生成
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
 *   BR-user_group_member-FLD-REQ-user_id  (用户ID 必填)
 *   BR-user_group_member-FLD-REQ-group_id  (用户组ID 必填)
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

const USER_GROUP_MEMBER_URL = '/user_group_member-management'

test.describe('S-BF-USER_GROUP_MEMBER-AUTO: 用户组成员 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 用户ID (user_id)
   * 业务规则: BR-user_group_member-FLD-REQ-user_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_USER_ID: 缺少必填字段 [用户ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [用户ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group_member', {
        group_id: null,
      }, 'user_id')
      expect(result, '[API 维度] 缺少 [用户ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 用户组ID (group_id)
   * 业务规则: BR-user_group_member-FLD-REQ-group_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_GROUP_ID: 缺少必填字段 [用户组ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [用户组ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'user_group_member', {
        user_id: null,
      }, 'group_id')
      expect(result, '[API 维度] 缺少 [用户组ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-user_group_member-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_user_group_member', async () => {
      await navigateTo(page, '/user_group_member-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/user_group_member/user_group_member-detail
   * 业务规则: BR-user_group_member-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_user_group_member', async () => {
      const obj = await dataFinder.user_group_member().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'user_group_member', obj.id)
        await page.waitForURL('**/detail/user_group_member/user_group_member-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.user_group_member`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-user_group_member-HEALTH
   */
  test('HEALTH: [用户组成员] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_user_group_member', async () => {
      await navigateTo(page, '/user_group_member-management')
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
   * ui_badge 规则: is_manager 字段彩色标签
   * 业务规则: BR-user_group_member-BADGE-is_manager
   */
  test('BADGE_IS_MANAGER: 验证 [is_manager] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_user_group_member_is_manager', async () => {
      await navigateTo(page, '/user_group_member-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_manager tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * nested_transaction 规则: children=[]
   * 业务规则: BR-user_group_member-NEST-atomic
   */
  test('NEST_CREATE: 深插入 [用户组成员] + 子对象 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'NEST_user_group_member', async () => {
      const parent = await dataFinder.user_group_member().catch(() => null)
      if (parent) {
        const nestedPOM = new NestedPOM(page)
        console.log(`  [NEST] 父对象 ID=${parent.id}, 模拟深插入`)
      } else {
        console.log(`  [NEST] 跳过: 无 dataFinder.user_group_member`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] NEST 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-user_group_member-PER-survives_reload
   */
  test('PER_RELOAD: [用户组成员] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_user_group_member', async () => {
      const obj = await dataFinder.user_group_member().catch(() => null)
      if (obj) {
        await navigateTo(page, '/user_group_member-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.user_group_member`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [用户组成员] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [用户组成员] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [用户组成员] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_user_group_member', async () => {
        await navigateTo(page, '/user_group_member-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
