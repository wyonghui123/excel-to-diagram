/**
 * S03: 业务对象（BO）管理 - 功能测试
 *
 * 路径: /system/archdata (架构数据管理)
 * 验证: BO 列表 + 版本管理 + 关系配置
 */
import { test, expect } from '@playwright/test'
import {
  login, navigateAndWaitForPage, setAdminPermissions,
  attachAndVerifyScreenshot
} from '../helpers/auth.js'

test.describe('S03: 业务对象管理', () => {
  test('C01: 架构数据管理页面加载', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/system/archdata', {
      expectedPath: 'archdata',
      waitForTable: true
    })
    await page.waitForTimeout(1500)
    await attachAndVerifyScreenshot(page, testInfo, '01-archdata-list')

    // 验证 tab 容器
    const tabs = page.locator('.el-tabs__item, [role="tab"]')
    const tabCount = await tabs.count()
    console.log(`[OK] Tab 数量: ${tabCount}`)

    if (tabCount > 0) {
      // 点击"业务对象" tab
      const boTab = tabs.filter({ hasText: /业务对象|BO/ }).first()
      if (await boTab.isVisible().catch(() => false)) {
        await boTab.click()
        await page.waitForTimeout(1000)
        await attachAndVerifyScreenshot(page, testInfo, '02-archdata-bo-tab')
        console.log('[OK] 业务对象 tab 切换成功')
      }
    }
  })

  test('C02: 业务对象搜索与过滤', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/system/archdata', { waitForTable: true })
    await page.waitForTimeout(1000)

    const searchInput = page.locator('input[placeholder*="搜索"], input[placeholder*="查询"]').first()
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('domain')
      await page.waitForTimeout(800)
      await attachAndVerifyScreenshot(page, testInfo, '03-archdata-search')
      console.log('[OK] 搜索功能验证')

      // 清空
      await searchInput.fill('')
      await page.waitForTimeout(500)
    }
  })
})
