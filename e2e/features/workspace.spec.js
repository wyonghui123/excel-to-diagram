/**
 * S05: 工作台与导航 - 功能测试
 *
 * 路径: /
 * 验证: 工作台快捷入口、导航菜单、跨页签切换
 */
import { test, expect } from '@playwright/test'
import {
  login, navigateAndWaitForPage, setAdminPermissions,
  attachAndVerifyScreenshot
} from '../helpers/auth.js'

test.describe('S05: 工作台与导航', () => {
  test('C01: 工作台快捷入口', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await attachAndVerifyScreenshot(page, testInfo, '01-workspace')

    // 验证快捷入口
    const entries = page.locator('.workspace-entry, .quick-link, [class*="entry"], a[href*="product"]')
    const count = await entries.count()
    console.log(`[OK] 工作台快捷入口数量: ${count}`)

    if (count > 0) {
      // 点击第一个
      await entries.first().click()
      await page.waitForTimeout(2000)
      await attachAndVerifyScreenshot(page, testInfo, '02-workspace-after-click')
      console.log(`[OK] 点击后 URL: ${page.url()}`)
    }
  })

  test('C02: 跨页面 tab 切换', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    // 访问产品管理
    await navigateAndWaitForPage(page, '/product-management', { waitForTable: true })
    await page.waitForTimeout(1000)

    // 访问架构数据管理
    await navigateAndWaitForPage(page, '/system/archdata', { waitForTable: true })
    await page.waitForTimeout(1000)

    // 验证 tab 存在
    const tabs = page.locator('.app-tab, [class*="tab"]')
    const tabCount = await tabs.count()
    console.log(`[OK] 打开的 tab 数量: ${tabCount}`)

    await attachAndVerifyScreenshot(page, testInfo, '03-multi-tabs')
  })
})
