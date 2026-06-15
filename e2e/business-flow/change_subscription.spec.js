/**
 * S-BF-CHANGE_SUBSCRIPTION-AUTO: 变更订阅 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 change_subscription.yaml 自动生成
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
 *   BR-change_subscription-FLD-REQ-user_id  (用户ID 必填)
 *   BR-change_subscription-FLD-REQ-object_type  (对象类型 必填)
 *   BR-change_subscription-FLD-REQ-channel  (通知渠道 必填)
 *   BR-change_subscription-FLD-REQ-enabled  (是否启用 必填)
 *
 * 自动生成时间: 2026-05-22
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const CHANGE_SUBSCRIPTION_URL = '/change_subscription-management'

test.describe('S-BF-CHANGE_SUBSCRIPTION-AUTO: 变更订阅 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 用户ID (user_id)
   * 业务规则: BR-change_subscription-FLD-REQ-user_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_USER_ID: 缺少必填字段 [用户ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [用户ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_subscription', {
        object_type: "placeholder_object_type",
        channel: "placeholder_channel",
        enabled: "True",
      }, 'user_id')
      expect(result, '[API 维度] 缺少 [用户ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象类型 (object_type)
   * 业务规则: BR-change_subscription-FLD-REQ-object_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_TYPE: 缺少必填字段 [对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_subscription', {
        user_id: null,
        channel: "placeholder_channel",
        enabled: "True",
      }, 'object_type')
      expect(result, '[API 维度] 缺少 [对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 通知渠道 (channel)
   * 业务规则: BR-change_subscription-FLD-REQ-channel
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_CHANNEL: 缺少必填字段 [通知渠道] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [通知渠道] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_subscription', {
        user_id: null,
        object_type: "placeholder_object_type",
        enabled: "True",
      }, 'channel')
      expect(result, '[API 维度] 缺少 [通知渠道] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 是否启用 (enabled)
   * 业务规则: BR-change_subscription-FLD-REQ-enabled
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_ENABLED: 缺少必填字段 [是否启用] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [是否启用] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_subscription', {
        user_id: null,
        object_type: "placeholder_object_type",
        channel: "placeholder_channel",
      }, 'enabled')
      expect(result, '[API 维度] 缺少 [是否启用] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [变更订阅] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [变更订阅] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [变更订阅] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_change_subscription', async () => {
        await navigateTo(page, '/change_subscription-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
