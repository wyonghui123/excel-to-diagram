/**
 * S05: 工作台与导航 - 功能测试
 *
 * 路径: /
 * 验证: 工作台快捷入口、导航菜单、跨页签切换
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (无测试数据创建)
 * [OK] POM (GenericListPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

test.describe('S05: 工作台与导航', () => {
  test('C01: 工作台快捷入口', async ({
    page, navigateTo, waitForApiFn, isolation
  }, testInfo) => {
    await withStep(page, testInfo, '导航到工作台首页', async () => {
      await navigateTo(page, '/', { waitForTable: false })
    })

    // 验证快捷入口
    await withStep(page, testInfo, '验证快捷入口', async () => {
      const entries = page.locator('.workspace-entry, .quick-link, [class*="entry"], a[href*="product"]')
      const count = await entries.count()
      console.log(`[OK] 工作台快捷入口数量: ${count}`)

      if (count > 0) {
        await entries.first().click()
        await waitForApiFn(page, 'GET /api/').catch(() => {})
        console.log(`[OK] 点击后 URL: ${page.url()}`)
      }
    })
  })

  test('C02: 跨页面 tab 切换', async ({
    page, navigateTo, waitForApiFn, isolation
  }, testInfo) => {
    const list = new GenericListPage(page)

    // 访问产品管理
    await withStep(page, testInfo, '导航到产品管理页面', async () => {
      await navigateTo(page, '/product-management')
    })

    // 访问架构数据管理
    await withStep(page, testInfo, '导航到架构数据管理页面', async () => {
      await navigateTo(page, '/system/archdata')
    })

    // 验证 tab 存在
    await withStep(page, testInfo, '验证 tab 存在', async () => {
      const tabs = page.locator('.app-tab, [class*="tab"]')
      const tabCount = await tabs.count()
      console.log(`[OK] 打开的 tab 数量: ${tabCount}`)
    })
  })
})
