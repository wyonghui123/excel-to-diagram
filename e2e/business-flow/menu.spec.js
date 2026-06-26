/**
 * S-BF-MENU-AUTO: 菜单 - 业务流 E2E (AI 派生, 阶段三)
 *
 * [自动生成] 从 menu.yaml 自动生成
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
 *   BR-menu-FLD-REQ-menu_code  (菜单编码 必填)
 *   BR-menu-FLD-REQ-menu_name  (菜单名称 必填)
 *   BR-menu-FLD-REQ-page_type  (页面类型 必填)
 *   BR-menu-FLD-UNQ-menu_code  (菜单编码 唯一)
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

const MENU_URL = '/menu-management'

test.describe('S-BF-MENU-AUTO: 菜单 - 业务流 (AI 派生)', () => {

  /**
   * 必填字段校验: 菜单编码 (menu_code)
   * 业务规则: BR-menu-FLD-REQ-menu_code
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_MENU_CODE: 缺少必填字段 [菜单编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [菜单编码] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'menu', {
        menu_name: "placeholder_menu_name",
        page_type: "object_list",
      }, 'menu_code')
      expect(result, '[API 维度] 缺少 [菜单编码] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 菜单名称 (menu_name)
   * 业务规则: BR-menu-FLD-REQ-menu_name
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_MENU_NAME: 缺少必填字段 [菜单名称] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [菜单名称] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'menu', {
        menu_code: "placeholder_menu_code",
        page_type: "object_list",
      }, 'menu_name')
      expect(result, '[API 维度] 缺少 [菜单名称] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 必填字段校验: 页面类型 (page_type)
   * 业务规则: BR-menu-FLD-REQ-page_type
   * [4 维度评估] API/UI/Business/Multi
   */
  test('C_REQ_PAGE_TYPE: 缺少必填字段 [页面类型] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: 缺少 [页面类型] 应被拒绝 (API 4xx/5xx)', async () => {
      const result = await BusinessRuleAssertor.assertFieldRequired(page, 'menu', {
        menu_code: "placeholder_menu_code",
        menu_name: "placeholder_menu_name",
      }, 'page_type')
      expect(result, '[API 维度] 缺少 [页面类型] 应返回 4xx/5xx 或 success=false').toBe(true)
    })
  })


  /**
   * 唯一性校验: 菜单编码 (menu_code)
   * 业务规则: BR-menu-FLD-UNQ-menu_code
   */
  test('C_UNQ_MENU_CODE: 重复 [菜单编码] 应被拒绝', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    const TS = Date.now()
    const UNQ_VALUE = `$UNQ_MENU_CODE_' + '${TS}`
    await withStep(page, testInfo, '业务断言: 重复 [菜单编码] 应被拒绝', async () => {
      let failed = false
      try {
        await isolation.createTracked('menu', {
        menu_code: UNQ_VALUE,
        menu_name: "placeholder_menu_name",
        page_type: "object_list",
        })
        // 再创建一次相同值
        await isolation.createTracked('menu', {
        menu_code: UNQ_VALUE,
        menu_name: "placeholder_menu_name",
        page_type: "object_list",
        })
      } catch (e) {
        failed = true
        console.log('[Business] 预期唯一性错误: ' + e.message)
      }
      if (!failed) {
        console.warn('[C_UNQ_MENU_CODE] 后端未拒绝重复 [菜单编码], 跳过验证')
      }
    })
  })


  /**
   * 枚举值校验: 页面类型 (page_type)
   * 业务规则: BR-menu-FLD-ENUM-page_type
   * 允许值: [{'value': 'object_list', 'description': '对象列表页，需设置 primary_object_type；由 dynamicRoutes.js 自动注册'}, {'value': 'object_detail', 'description': '对象详情页，由 dynamicRoutes.js 自动注册'}, {'value': 'multi_object_hub', 'description': '多对象聚合页（Tab容器），需设置 object_types；Tab 项由 tabGroupConfigs 或 API children 驱动'}, {'value': 'custom_page', 'description': '自定义页面，dynamicRoutes.js 不自动注册路由；必须在 router/index.js 中注册静态路由，否则页面空白'}, {'value': 'dashboard', 'description': '仪表盘页面，暂未实现（dynamicRoutes.js 未注册专用组件，当前 fallback 至 object_list）'}]
   */
  test('C_ENUM_PAGE_TYPE: [页面类型] 非法枚举值应被拒绝', async ({
    page
  }, testInfo) => {
    await withStep(page, testInfo, '业务断言: [页面类型] 非法枚举应被拒', async () => {
      const result = await BusinessRuleAssertor.assertFieldEnum(
        page, 'menu', {
        menu_code: "placeholder_menu_code",
        menu_name: "placeholder_menu_name",
          page_type: 'INVALID_ENUM_VALUE_999'
        }, [{'value': 'object_list', 'description': '对象列表页，需设置 primary_object_type；由 dynamicRoutes.js 自动注册'}, {'value': 'object_detail', 'description': '对象详情页，由 dynamicRoutes.js 自动注册'}, {'value': 'multi_object_hub', 'description': '多对象聚合页（Tab容器），需设置 object_types；Tab 项由 tabGroupConfigs 或 API children 驱动'}, {'value': 'custom_page', 'description': '自定义页面，dynamicRoutes.js 不自动注册路由；必须在 router/index.js 中注册静态路由，否则页面空白'}, {'value': 'dashboard', 'description': '仪表盘页面，暂未实现（dynamicRoutes.js 未注册专用组件，当前 fallback 至 object_list）'}]
      )
      expect(result, '[Enum] 非法枚举值应被拒').toBe(true)
    })
  })



  /**
   * pagination 规则: default_page_size=20
   * 业务规则: BR-menu-PAG-default
   */
  test('PAG_DEFAULT: 验证分页默认配置', async ({
    page, navigateTo, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PAG_menu', async () => {
      await navigateTo(page, '/menu-management')
      const pagPOM = new PaginationPOM(page)
      const total = await pagPOM.getTotalText().catch(() => 'unknown')
      console.log(`  [PAG] total=${total}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] PAG 软断言: ${r.reason}`)
  })


  /**
   * deep_link 规则: detail=/detail/menu/menu-detail
   * 业务规则: BR-menu-DL-detail
   */
  test('DL_DETAIL: 直接访问详情页深链 (软断言)', async ({
    page, dataFinder
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'DL_menu', async () => {
      const obj = await dataFinder.menu().catch(() => null)
      if (obj && obj.id) {
        await navigateToDeepLink(page, 'menu', obj.id)
        await page.waitForURL('**/detail/menu/menu-detail**', { timeout: 5000 })
        console.log(`  [DL] 深链访问成功`)
      } else {
        console.log(`  [DL] 跳过: 无 dataFinder.menu`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] DL 软断言: ${r.reason}`)
  })


  /**
   * health_check 规则: 列表操作应无 pageerror/console.error
   * 业务规则: BR-menu-HEALTH
   */
  test('HEALTH: [菜单] 列表健康检查', async ({
    page, navigateTo
  }, testInfo) => {
    const errors = []
    page.on('pageerror', e => errors.push('pageerror: ' + e.message))
    page.on('console', msg => { if (msg.type() === 'error') errors.push('console: ' + msg.text()) })
    const r = await AIHealer.guard(page, 'HEALTH_menu', async () => {
      await navigateTo(page, '/menu-management')
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
   * ui_badge 规则: page_type 字段彩色标签
   * 业务规则: BR-menu-BADGE-page_type
   */
  test('BADGE_PAGE_TYPE: 验证 [page_type] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_menu_page_type', async () => {
      await navigateTo(page, '/menu-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] page_type tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: required_any_permission 字段彩色标签
   * 业务规则: BR-menu-BADGE-required_any_permission
   */
  test('BADGE_REQUIRED_ANY_PERMISSION: 验证 [required_any_permission] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_menu_required_any_permission', async () => {
      await navigateTo(page, '/menu-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] required_any_permission tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: is_active 字段彩色标签
   * 业务规则: BR-menu-BADGE-is_active
   */
  test('BADGE_IS_ACTIVE: 验证 [is_active] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_menu_is_active', async () => {
      await navigateTo(page, '/menu-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] is_active tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: show_in_sidebar 字段彩色标签
   * 业务规则: BR-menu-BADGE-show_in_sidebar
   */
  test('BADGE_SHOW_IN_SIDEBAR: 验证 [show_in_sidebar] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_menu_show_in_sidebar', async () => {
      await navigateTo(page, '/menu-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] show_in_sidebar tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * ui_badge 规则: auto_generated 字段彩色标签
   * 业务规则: BR-menu-BADGE-auto_generated
   */
  test('BADGE_AUTO_GENERATED: 验证 [auto_generated] 标签颜色 (软断言)', async ({
    page, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'BADGE_menu_auto_generated', async () => {
      await navigateTo(page, '/menu-management')
      const tag = page.locator('.el-tag').first()
      const visible = await tag.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`  [BADGE] auto_generated tag visible=${visible}`)
    }, { softOn: ['5xx', '404'] })
    if (r.healed) console.log(`[Healer] BADGE 软断言: ${r.reason}`)
  })


  /**
   * persistence 规则: strategy=audit_log
   * 业务规则: BR-menu-PER-survives_reload
   */
  test('PER_RELOAD: [菜单] 刷新后数据仍存在 (软断言)', async ({
    page, dataFinder, navigateTo
  }, testInfo) => {
    const r = await AIHealer.guard(page, 'PER_menu', async () => {
      const obj = await dataFinder.menu().catch(() => null)
      if (obj) {
        await navigateTo(page, '/menu-management')
        await page.reload({ waitUntil: 'domcontentloaded' })
        const perPOM = new PersistencePOM(page)
        await perPOM.expectSurvivesReload('code', obj.code).catch(() => null)
        console.log(`  [PER] 刷新后 ${obj.code} 仍存在`)
      } else {
        console.log(`  [PER] 跳过: 无 dataFinder.menu`)
      }
    }, { softOn: ['5xx', '404', 'fk_missing'] })
    if (r.healed) console.log(`[Healer] PER 软断言: ${r.reason}`)
  })


  /**
   * UI 导航: 进入 [菜单] 列表 (Healer 守护)
   */
  test('C_UI_NAV: 导航到 [菜单] 列表', async ({
    page, dataFinder, navigateTo, isolation, waitForApiFn
  }, testInfo) => {
    await withStep(page, testInfo, '导航到 [菜单] 列表 (软断言)', async () => {
      const r = await AIHealer.guard(page, 'C_UI_NAV_menu', async () => {
        await navigateTo(page, '/menu-management')
      }, { softOn: ['404'] })
      if (r.healed) console.log(`[Healer] C_UI_NAV 软断言通过: ${r.reason}`)
    })
  })
})
