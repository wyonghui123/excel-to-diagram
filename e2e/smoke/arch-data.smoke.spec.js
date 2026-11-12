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
  setupCompleteArchData,
  runCleanup
} from '../helpers/auth.js'
import { listRows } from '../helpers/responsive.js'

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

    const tabs = page.locator('.momp-tab-btn')
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

    // [补测试数据] 仅选到空版本时 5 个 Tab 全为 0 行，用例无法验证“列表可查看”。
    // setupCompleteArchData 会在所选版本内确保 领域/子领域/服务模块/业务对象 各有数据
    const seeded = await setupCompleteArchData(page)
    const pv = { product: seeded.product, version: seeded.version }
    console.log(`[OK] 测试数据: product=${pv.product.id}, version=${pv.version.id}`)

    // 直接通过 URL 参数选择产品和版本
    await page.goto(`/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, {
      waitUntil: 'domcontentloaded'
    })

    // Tab 依赖 versionContext.selectedVersionId；URL 恢复受版本列表加载速度影响，不能只靠固定等待
    const navTabs = page.locator('.momp-tab-btn')
    const tabsReady = await navTabs.first().waitFor({ state: 'visible', timeout: 6000 }).then(() => true).catch(() => false)
    if (!tabsReady) {
      // 兜底：通过全局工具栏手动选产品/版本（避免版本列表加载慢导致 URL 参数未生效）
      console.log('[warn] URL 参数未生效，改用工具栏选择产品/版本')
      const productSelect = page.locator('.gt-selector').first().locator('.el-select').first()
      await productSelect.click()
      const productOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: pv.product.name }).first()
      await productOption.waitFor({ state: 'visible', timeout: 5000 })
      await productOption.click()

      const versionSelect = page.locator('.gt-selector').nth(1).locator('.el-select').first()
      await versionSelect.click()
      const versionOption = page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: pv.version.name }).first()
      await versionOption.waitFor({ state: 'visible', timeout: 5000 })
      await versionOption.click()

      await navTabs.first().waitFor({ state: 'visible', timeout: 8000 })
    }

    await attachAndVerifyScreenshot(page, testInfo, '02-archdata-with-version', { expectedPath: 'archdata' })

    const tabNames = ['领域', '子领域', '服务模块', '业务对象', '关联关系']
    const tabResults = []

    for (let i = 0; i < tabNames.length; i++) {
      const tab = page.locator(`.momp-tab-btn:has-text("${tabNames[i]}")`).first()
      if (await tab.isVisible().catch(() => false)) {
        await tab.click()
        // 列表由 MetaListPage 异步加载：桌面为 el-table，窄屏为 meta-card-list
        await page.locator('.el-table, .meta-card-list').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        await page.waitForTimeout(500)

        const rowCount = await listRows(page).count()
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
    const tabs = page.locator('.momp-tab-btn')
    const tabCount = await tabs.count()
    expect(tabCount).toBeGreaterThan(0)
    console.log(`[OK] 验证通过: ${tabCount} 个 Tab 可见`)
  })
})
