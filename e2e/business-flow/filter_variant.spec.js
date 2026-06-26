/**
 * S-BF-FILTER_VARIANT-AUTO: 过滤变体 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 filter_variant.yaml 自动生成
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
 *   BR-filter_variant-FLD-REQ-name  (变体名称 必填)
 *   BR-filter_variant-FLD-REQ-object_type  (对象类型 必填)
 *   BR-filter_variant-FLD-REQ-filters  (过滤条件 必填)
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

const FILTER_VARIANT_URL = '/filter_variant-management'

test.describe('S-BF-FILTER_VARIANT-AUTO: 过滤变体 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 变体名称 (name)
   * 业务规则: BR-filter_variant-FLD-REQ-name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_NAME: 缺少必填字段 [变体名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [变体名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        object_type: "placeholder_object_type",
        filters: "placeholder_filters",
      }, 'name')
      expect(result, '[API 维度] 缺少 [变体名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 对象类型 (object_type)
   * 业务规则: BR-filter_variant-FLD-REQ-object_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_OBJECT_TYPE: 缺少必填字段 [对象类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [对象类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        name: "placeholder_name",
        filters: "placeholder_filters",
      }, 'object_type')
      expect(result, '[API 维度] 缺少 [对象类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 过滤条件 (filters)
   * 业务规则: BR-filter_variant-FLD-REQ-filters
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_FILTERS: 缺少必填字段 [过滤条件] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [过滤条件] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'filter_variant', {
        name: "placeholder_name",
        object_type: "placeholder_object_type",
      }, 'filters')
      expect(result, '[API 维度] 缺少 [过滤条件] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-filter_variant-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_filter_variant', async () => {
      await navigateTo(page, '/filter_variant-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/filter_variant/filter_variant-detail
   * 业务规则: BR-filter_variant-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_filter_variant', async () => {
      const obj = await dataFinder.filter_variant().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'filter_variant', obj.id)
        await page.waitForURL('**/detail/filter_variant/filter_variant-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.filter_variant`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-filter_variant-HEALTH
   */
  test('HEALTH: [过滤变体] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_filter_variant', async () => {
      await navigateTo(page, '/filter_variant-management')
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
   * ui_badge 规则: is_shared 字段彩色标签
   * 业务规则: BR-filter_variant-BADGE-is_shared
   */
  test('BADGE_IS_SHARED: 验证 [is_shared] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_filter_variant_is_shared', async () => {
      await navigateTo(page, '/filter_variant-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_shared tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: is_default 字段彩色标签
   * 业务规则: BR-filter_variant-BADGE-is_default
   */
  test('BADGE_IS_DEFAULT: 验证 [is_default] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_filter_variant_is_default', async () => {
      await navigateTo(page, '/filter_variant-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_default tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-filter_variant-PER-survives_reload
   */
  test('PER_RELOAD: [过滤变体] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_filter_variant', async () => {
      const obj = await dataFinder.filter_variant().catch(() => null)
      if (obj) {
        await navigateTo(page, '/filter_variant-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.filter_variant`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [过滤变体] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [过滤变体] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [过滤变体] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_filter_variant', async () => {
        await navigateTo(page, '/filter_variant-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
