/**
 * S02: 架构数据 - 页面导航与对象列表 - 冒烟测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 *
 * [NEW v3.19] 测试数据管理:
 * - 使用 ensureProductWithVersion() 自动确保测试数据存在
 * - 不再依赖 findProductWithVersion() 可能返回 null 导致测试跳过
 */
import { test, expect } from '@playwright/test'
import {
  login,
  navigateAndWaitForPage,
  setAdminPermissions,
  attachAndVerifyScreenshot,
  ensureProductWithVersion,
  runCleanup
} from '../helpers/auth.js'

test.describe('S02: 架构数据 - 页面导航与对象列表', () => {
  // 每个测试后自动清理
  test.afterEach(async () => {
    await runCleanup()
  })

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
      console.log('[INFO] 未选择产品版本时 Tab 不显示（正常行为）')
    }
  })

  test('C05: 所有对象列表查看验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    await navigateAndWaitForPage(page, '/system/archdata', { expectedPath: 'archdata', waitForTable: false })
    await page.waitForTimeout(500)

    // [NEW v3.19] 使用 ensureProductWithVersion 确保测试数据存在
    // 不再依赖 findProductWithVersion 可能返回 null
    const pv = await ensureProductWithVersion(page)
    console.log(`[OK] 测试数据: product=${pv.product.id}, version=${pv.version.id}`)

    // 直接通过 URL 参数选择产品和版本
    await page.goto(`/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, {
      waitUntil: 'domcontentloaded'
    })
    await page.waitForTimeout(2000)

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
        console.log(`[INFO] Tab "${tabNames[i]}" 不可见`)
      }
    }

    const tabsWithData = tabResults.filter(t => t.rows > 0)
    expect(tabsWithData.length).toBeGreaterThan(0)
    console.log(`[OK] ${tabsWithData.length}/${tabNames.length} 个 Tab 有数据`)
  })

  test('C06: 使用 ensureProductWithVersion 的数据驱动测试', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    // [NEW v3.19] 演示如何使用 ensureProductWithVersion
    // 自动创建测试数据，不会跳过测试
    const pv = await ensureProductWithVersion(page, {
      productName: 'Smoke Test Product',
      versionName: 'V1.0-Smoke'
    })
    console.log(`[OK] 创建测试数据: product=${pv.product.id}, version=${pv.version.id}`)

    // 验证数据存在
    expect(pv.product).toBeDefined()
    expect(pv.product.id).toBeGreaterThan(0)
    expect(pv.version).toBeDefined()
    expect(pv.version.id).toBeGreaterThan(0)

    // 使用 URL 参数直接导航到页面
    await navigateAndWaitForPage(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, {
      expectedPath: 'archdata',
      waitForTable: false
    })
    await page.waitForTimeout(1500)

    await attachAndVerifyScreenshot(page, testInfo, '04-data-driven-test', { expectedPath: 'archdata' })

    // 验证 Tab 显示（产品版本已选择）
    const tabs = page.locator('.el-tabs__item')
    const tabCount = await tabs.count()
    expect(tabCount).toBeGreaterThan(0)
    console.log(`[OK] 验证通过: ${tabCount} 个 Tab 可见`)
  })
})
