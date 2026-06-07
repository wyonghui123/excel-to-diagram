/**
 * S02: 架构数据 - 页面导航与对象列表 - 冒烟测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 */
import { test, expect } from '@playwright/test'
import { login, navigateAndWaitForPage, setAdminPermissions, attachAndVerifyScreenshot, findProductWithVersion } from '../helpers/auth.js'

test.describe('S02: 架构数据 - 页面导航与对象列表', () => {
  test('C04: 页面导航与布局验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    await navigateAndWaitForPage(page, '/system/archdata', { expectedPath: 'archdata', waitForTable: false })
    await page.waitForTimeout(1500)

    await attachAndVerifyScreenshot(page, testInfo, '01-archdata-page', { expectedPath: 'archdata' })

    const globalToolbar = page.locator('.global-toolbar')
    const hasToolbar = await globalToolbar.isVisible().catch(() => false)
    if (!hasToolbar) {
      await page.waitForTimeout(2000)
    }
    const hasToolbarRetry = await globalToolbar.isVisible().catch(() => false)
    expect(hasToolbarRetry).toBe(true)
    console.log('[OK] 全局工具栏可见')

    const productSelector = page.locator('.gt-selector').first()
    const hasProductSelector = await productSelector.isVisible().catch(() => false)
    if (hasProductSelector) console.log('[OK] 产品选择器可见')

    const versionSelector = page.locator('.gt-selector').nth(1)
    const hasVersionSelector = await versionSelector.isVisible().catch(() => false)
    if (hasVersionSelector) console.log('[OK] 版本选择器可见')

    const actionsArea = page.locator('.gt-actions')
    if (await actionsArea.isVisible().catch(() => false)) console.log('[OK] 操作按钮区可见')

    const tabs = page.locator('.el-tabs__item, .momp-tabs .el-tabs__item')
    const tabCount = await tabs.count()
    if (tabCount > 0) {
      console.log(`[OK] Tab 区域有 ${tabCount} 个 Tab`)
    } else {
      console.log('[WARNING] 未选择产品版本时 Tab 不显示（正常行为）')
    }
  })

  test('C05: 所有对象列表查看验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    await navigateAndWaitForPage(page, '/system/archdata', { expectedPath: 'archdata', waitForTable: false })
    await page.waitForTimeout(500)

    const pv = await findProductWithVersion(page)
    if (!pv) {
      console.log('[WARNING] 无可用的产品版本数据，跳过测试')
      test.skip()
      return
    }

    const productSelect = page.locator('.gt-selector').first().locator('.gt-select')
    await productSelect.click()
    await page.waitForTimeout(300)
    const productOption = page.locator(`.el-select-dropdown__item:has-text("${pv.product.name || pv.product.id}")`).first()
    await productOption.click()
    await page.waitForTimeout(500)

    const versionSelect = page.locator('.gt-selector').nth(1).locator('.gt-select')
    await versionSelect.click()
    await page.waitForTimeout(300)
    const versionOption = page.locator(`.el-select-dropdown__item:has-text("${pv.version.name || pv.version.id}")`).first()
    await versionOption.click()
    await page.waitForTimeout(1500)

    await attachAndVerifyScreenshot(page, testInfo, '02-archdata-with-version', { expectedPath: 'archdata' })

    const tabNames = ['领域', '子领域', '服务模块', '业务对象', '关联关系']
    const tabResults = []

    for (let i = 0; i < tabNames.length; i++) {
      const tab = page.locator(`.el-tabs__item:has-text("${tabNames[i]}")`).first()
      if (await tab.isVisible().catch(() => false)) {
        await tab.click()
        await page.waitForTimeout(1000)

        const tableRows = page.locator('.el-table__body tr')
        const rowCount = await tableRows.count()
        tabResults.push({ name: tabNames[i], rows: rowCount })

        if (i === 0) {
          await attachAndVerifyScreenshot(page, testInfo, `03-tab-${tabNames[i]}`, { expectedPath: 'archdata' })
        }

        console.log(`[OK] Tab "${tabNames[i]}": ${rowCount} 行数据`)
      } else {
        console.log(`[WARNING] Tab "${tabNames[i]}" 不可见`)
      }
    }

    const tabsWithData = tabResults.filter(t => t.rows > 0)
    expect(tabsWithData.length).toBeGreaterThan(0)
    console.log(`[OK] ${tabsWithData.length}/${tabNames.length} 个 Tab 有数据`)
  })
})
