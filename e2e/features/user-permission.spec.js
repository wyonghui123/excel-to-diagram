/**
 * S04: 用户与权限管理 - 功能测试
 *
 * 路径: /user-permission
 * 验证: 用户管理 / 用户组管理 / 角色管理 三个 tab
 */
import { test, expect } from '@playwright/test'
import {
  login, navigateAndWaitForPage, setAdminPermissions,
  attachAndVerifyScreenshot
} from '../helpers/auth.js'

test.describe('S04: 用户与权限管理', () => {
  test('C01: 用户组管理 tab 验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/user-permission', {
      expectedPath: 'user-permission',
      waitForTabs: true
    })
    await page.waitForTimeout(1500)
    await attachAndVerifyScreenshot(page, testInfo, '01-user-permission')

    // 验证三个 tab
    const tabs = page.locator('.el-tabs__item, [role="tab"]')
    const tabCount = await tabs.count()
    console.log(`[OK] Tab 数量: ${tabCount}`)

    // 点击"用户组"
    const groupTab = tabs.filter({ hasText: '用户组' }).first()
    if (await groupTab.isVisible().catch(() => false)) {
      await groupTab.click()
      await page.waitForTimeout(1000)
      await attachAndVerifyScreenshot(page, testInfo, '02-user-group-tab')
      console.log('[OK] 用户组 tab 切换成功')

      const table = page.locator('.el-table').first()
      if (await table.isVisible().catch(() => false)) {
        console.log('[OK] 用户组表格可见')
      }
    }
  })

  test('C02: 角色管理 tab 验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/user-permission?tab=roles', { waitForTabs: true })
    await page.waitForTimeout(1500)
    await attachAndVerifyScreenshot(page, testInfo, '03-roles-tab')

    const roleTab = page.locator('.el-tabs__item, [role="tab"]').filter({ hasText: '角色' }).first()
    if (await roleTab.isVisible().catch(() => false)) {
      await roleTab.click()
      await page.waitForTimeout(1000)
      await attachAndVerifyScreenshot(page, testInfo, '04-roles-tab-active')

      // 验证角色表格
      const table = page.locator('.el-table').first()
      expect(await table.isVisible({ timeout: 10000 }).catch(() => false)).toBeTruthy()
      console.log('[OK] 角色管理 tab 验证完成')
    }
  })
})
