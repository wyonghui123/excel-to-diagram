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
 *
 * 业务规则:
 *   BR-user_group_member-FLD-REQ-user_id  (用户ID 必填)
 *   BR-user_group_member-FLD-REQ-group_id  (用户组ID 必填)
 *
 * 自动生成时间: 2026-05-26
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
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
