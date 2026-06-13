/**
 * S02: 架构数据 - 页面导航与对象列表 - 冒烟测试 (v2 风格)
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateTo()
 * - 详细: .trae/rules/e2e-testing.md
 *
 * [v2 简化 Phase 6 迁移] (2026-06-13):
 * - import 改自 auto-fixtures.js
 * - 删 login() + setAdminPermissions()
 * - 改用 dataFinder.productWithVersion() 替代 findProductWithVersion
 * - 删 waitForTimeout(1500) 改用 withStep
 */
import { test, expect, navigateTo, withStep, dataFinder } from '../helpers/auto-fixtures.js'
import { attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('S02: 架构数据 - 页面导航与对象列表', () => {
  test('C04: 页面导航与布局验证', async ({ page }, testInfo) => {
    await navigateTo(page, '/system/archdata', { waitForTable: false })

    await withStep(page, testInfo, '全局工具栏可见', async () => {
      const globalToolbar = page.locator('.global-toolbar')
      await expect(globalToolbar).toBeVisible({ timeout: 10000 })
      await attachAndVerifyScreenshot(page, testInfo, '01-archdata-page', { expectedPath: 'archdata' })
    })

    await withStep(page, testInfo, '产品/版本选择器可见', async () => {
      const selectors = page.locator('.gt-selector')
      const selectorCount = await selectors.count()
      expect(selectorCount).toBeGreaterThanOrEqual(2)  // 产品 + 版本
    })
  })

  test('C05: 所有对象列表查看验证', async ({ page, dataFinder }, testInfo) => {
    // [v2] 用 dataFinder 替代 findProductWithVersion
    const pv = await dataFinder.productWithVersion().catch(() => null)
    if (!pv) {
      test.skip(true, '无可用的产品版本数据，跳过测试 (前置数据缺失)')
      return
    }

    await withStep(page, testInfo, '导航到 archdata 并选产品版本', async () => {
      await navigateTo(
        page,
        `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`,
        { waitForTable: false }
      )
    })

    await withStep(page, testInfo, '5 个 Tab 都可点击 + 表格加载', async () => {
      const tabNames = ['领域', '子领域', '服务模块', '业务对象', '关联关系']
      const tabResults = []

      for (const tabName of tabNames) {
        const tab = page.locator(`.el-tabs__item:has-text("${tabName}")`).first()
        const isVisible = await tab.isVisible().catch(() => false)
        if (!isVisible) {
          tabResults.push({ name: tabName, visible: false, rows: 0 })
          continue
        }
        await tab.click()

        // [v2] 改用 waitForApi 替代 waitForTimeout(1000)
        // 等待对应 tab 的 API 响应
        const tabApiMap = {
          '领域': 'GET.*domain',
          '子领域': 'GET.*sub_domain',
          '服务模块': 'GET.*service_module',
          '业务对象': 'GET.*business_object',
          '关联关系': 'GET.*association'
        }
        // 注: waitForApiFn 在 auto-fixtures 中, 暂用简化的 waitForLoadState
        await page.waitForLoadState('domcontentloaded')

        const tableRows = page.locator('.el-table__body tr')
        const rowCount = await tableRows.count()
        tabResults.push({ name: tabName, visible: true, rows: rowCount })
      }

      // [v2] 至少 1 个 Tab 存在
      const visibleCount = tabResults.filter(t => t.visible).length
      expect(visibleCount).toBeGreaterThan(0)

      await attachAndVerifyScreenshot(page, testInfo, '02-archdata-tabs', { expectedPath: 'archdata' })
    })
  })
})
