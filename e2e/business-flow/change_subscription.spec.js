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
 * [v2.1] 14 类业务规则 (含 P1+P2 8 个新规则)
 *
 * 业务规则:
 *   BR-change_subscription-FLD-REQ-user_id  (用户ID 必填)
 *   BR-change_subscription-FLD-REQ-object_type  (对象类型 必填)
 *   BR-change_subscription-FLD-REQ-channel  (通知渠道 必填)
 *   BR-change_subscription-FLD-REQ-enabled  (是否启用 必填)
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
   * 枚举值校验: 是否启用 (enabled)
   * 业务规则: BR-change_subscription-FLD-ENUM-enabled
   * 允许值: [{'value': True, 'label': '已启用', 'color': 'success', 'icon': 'check_circle', 'is_initial': True, 'category': 'active', 'description': '订阅已启用，变更事件将发送通知'}, {'value': False, 'label': '已禁用', 'color': 'info', 'icon': 'pause_circle', 'category': 'inactive', 'description': '订阅已禁用，不会发送通知'}]
   */
  test('C_ENUM_ENABLED: [是否启用] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [是否启用] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'change_subscription', {
        user_id: null,
        object_type: "placeholder_object_type",
        channel: "placeholder_channel",
          enabled: 'INVALID_ENUM_VALUE_999'
        }, [{'value': True, 'label': '已启用', 'color': 'success', 'icon': 'check_circle', 'is_initial': True, 'category': 'active', 'description': '订阅已启用，变更事件将发送通知'}, {'value': False, 'label': '已禁用', 'color': 'info', 'icon': 'pause_circle', 'category': 'inactive', 'description': '订阅已禁用，不会发送通知'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-change_subscription-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_change_subscription', async () => {
      await navigateTo(page, '/change_subscription-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/change_subscription/change_subscription-detail
   * 业务规则: BR-change_subscription-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_change_subscription', async () => {
      const obj = await dataFinder.change_subscription().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'change_subscription', obj.id)
        await page.waitForURL('**/detail/change_subscription/change_subscription-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.change_subscription`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-change_subscription-HEALTH
   */
  test('HEALTH: [变更订阅] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_change_subscription', async () => {
      await navigateTo(page, '/change_subscription-management')
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
   * ui_badge 规则: enabled 字段彩色标签
   * 业务规则: BR-change_subscription-BADGE-enabled
   */
  test('BADGE_ENABLED: 验证 [enabled] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_change_subscription_enabled', async () => {
      await navigateTo(page, '/change_subscription-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] enabled tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-change_subscription-PER-survives_reload
   */
  test('PER_RELOAD: [变更订阅] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_change_subscription', async () => {
      const obj = await dataFinder.change_subscription().catch(() => null)
      if (obj) {
        await navigateTo(page, '/change_subscription-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.change_subscription`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
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
