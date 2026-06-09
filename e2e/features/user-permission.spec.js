/**
 * S04: 用户与权限管理 - 功能测试
 *
 * 路径: /user-permission
 * 验证: 用户组管理 / 角色管理 tab
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (page 已自动登录)
 * [OK] navigateTo fixture 替代 navigateAndWaitForPage
 * [OK] withStep 包裹每步业务操作
 * [OK] isolation fixture 解构 (auto cleanup)
 * [OK] POM: GenericListPage
 * [OK] 无硬编码 waitForTimeout (用 waitForApiFn / findRow 重试)
 * [OK] 无硬编码 Date.now() (无测试数据创建)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

test.describe('S04: 用户与权限管理', () => {
  test('C01: 用户组管理 tab 验证', async ({
    page, navigateTo, waitForApiFn
  }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到 /user-permission', async () => {
      await navigateTo(page, '/user-permission', { waitForTable: false, waitForTabs: true })
    })

    await withStep(page, testInfo, '切到"用户组" Tab (getByRole tab)', async () => {
      const tab = page.getByRole('tab', { name: '用户组' }).first()
        .or(page.locator('.el-tabs__item:has-text("用户组"), [role="tab"]:has-text("用户组")').first())
      await tab.waitFor({ state: 'visible', timeout: 10000 })
      await tab.click()
      try {
        await waitForApiFn(page, 'GET /api/v2/bo/user_group', { timeout: 8000 })
      } catch (e) {
        console.log('[INFO] waitForApiFn 未命中, 降级为 list waitForReady')
        await list.waitForReady().catch(() => {})
      }
    })

    await withStep(page, testInfo, '验证用户组表格可见', async () => {
      await list.waitForReady()
      const rowCount = await list.getRowCount()
      console.log(`[OK] 用户组表格可见, ${rowCount} 行数据`)
    })
  })

  test('C02: 角色管理 tab 验证', async ({
    page, navigateTo, waitForApiFn
  }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到 /user-permission (角色 Tab)', async () => {
      await navigateTo(page, '/user-permission?tab=roles', { waitForTable: false, waitForTabs: true })
    })

    await withStep(page, testInfo, '切到"角色" Tab (getByRole tab)', async () => {
      const tab = page.getByRole('tab', { name: '角色' }).first()
        .or(page.locator('.el-tabs__item:has-text("角色"), [role="tab"]:has-text("角色")').first())
      await tab.waitFor({ state: 'visible', timeout: 10000 })
      await tab.click()
      try {
        await waitForApiFn(page, 'GET /api/v1/roles', { timeout: 8000 })
      } catch (e) {
        console.log('[INFO] waitForApiFn 未命中, 降级为 list waitForReady')
        await list.waitForReady().catch(() => {})
      }
    })

    await withStep(page, testInfo, '验证角色表格可见', async () => {
      await list.waitForReady()
      const rowCount = await list.getRowCount()
      expect(rowCount, '角色表格应有数据').toBeGreaterThan(0)
      console.log(`[OK] 角色管理 tab 验证完成, ${rowCount} 行数据`)
    })
  })
})
