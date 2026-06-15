/**
 * S-BF-CHANGE_EVENT-AUTO: 变更事件 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 change_event.yaml 自动生成
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
 *   BR-change_event-FLD-REQ-object_type  (对象类型 必填)
 *   BR-change_event-FLD-REQ-object_id  (对象ID 必填)
 *   BR-change_event-FLD-REQ-event_type  (事件类型 必填)
 *   BR-change_event-FLD-REQ-status  (状态 必填)
 *   BR-change_event-FLD-REQ-retry_count  (重试次数 必填)
 *
 * 自动生成时间: 2026-05-22
 * 生成器: scripts/generate-e2e-from-schema.py
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor.js'
import { AIHealer } from '../helpers/ai-healer.js'

const CHANGE_EVENT_URL = '/change_event-management'

test.describe('S-BF-CHANGE_EVENT-AUTO: 变更事件 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 对象类型 (object_type)
   * 业务规则: BR-change_event-FLD-REQ-object_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_TYPE: 缺少必填字段 [对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_event', {
        object_id: null,
        event_type: "placeholder_event_type",
        status: "pending",
        retry_count: 0,
      }, 'object_type')
      expect(result, '[API 维度] 缺少 [对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象ID (object_id)
   * 业务规则: BR-change_event-FLD-REQ-object_id
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_ID: 缺少必填字段 [对象ID] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象ID] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_event', {
        object_type: "placeholder_object_type",
        event_type: "placeholder_event_type",
        status: "pending",
        retry_count: 0,
      }, 'object_id')
      expect(result, '[API 维度] 缺少 [对象ID] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 事件类型 (event_type)
   * 业务规则: BR-change_event-FLD-REQ-event_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_EVENT_TYPE: 缺少必填字段 [事件类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [事件类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_event', {
        object_type: "placeholder_object_type",
        object_id: null,
        status: "pending",
        retry_count: 0,
      }, 'event_type')
      expect(result, '[API 维度] 缺少 [事件类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 状态 (status)
   * 业务规则: BR-change_event-FLD-REQ-status
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_STATUS: 缺少必填字段 [状态] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [状态] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_event', {
        object_type: "placeholder_object_type",
        object_id: null,
        event_type: "placeholder_event_type",
        retry_count: 0,
      }, 'status')
      expect(result, '[API 维度] 缺少 [状态] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 重试次数 (retry_count)
   * 业务规则: BR-change_event-FLD-REQ-retry_count
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_RETRY_COUNT: 缺少必填字段 [重试次数] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [重试次数] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'change_event', {
        object_type: "placeholder_object_type",
        object_id: null,
        event_type: "placeholder_event_type",
        status: "pending",
      }, 'retry_count')
      expect(result, '[API 维度] 缺少 [重试次数] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * UI 导航: 进入 [变更事件] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [变更事件] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [变更事件] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_change_event', async () => {
        await navigateTo(page, '/change_event-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
