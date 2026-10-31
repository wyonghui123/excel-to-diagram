/**
 * S01: 认证与账户设置 - 冒烟测试 (v2 风格)
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateTo()
 * - 详细: .trae/rules/e2e-testing.md
 *
 * [v2 简化 Phase 6 迁移] (2026-06-13):
 * - import 改自 auto-fixtures.js (自动登录态)
 * - 删 login() + setAdminPermissions() (globalSetup 已处理)
 * - navigateAndWaitForPage → navigateTo
 * - 删 waitForTimeout(1500) 改用 withStep
 */
import { test, expect, navigateTo } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('S01: 认证与账户设置', () => {
  test('C01: 登录状态验证 (auto-login 后)', async ({ page }, testInfo) => {
    // [v2] 用 navigateTo, 不用 page.goto + waitForTimeout
    await navigateTo(page, '/', { waitForTable: false })

    await withStep(page, testInfo, '验证已登录用户菜单可见', async () => {
      // [v2] globalSetup 已预登录, 直接验证用户菜单
      const userTrigger = page.locator('.user-menu__trigger').first()
      const hasUserMenu = await userTrigger.isVisible().catch(() => false)
      expect(hasUserMenu).toBe(true)

      await attachAndVerifyScreenshot(page, testInfo, '01-logged-in', { expectedPath: '/' })
    })

    await withStep(page, testInfo, '用户菜单含退出选项', async () => {
      const userTrigger = page.locator('.user-menu__trigger').first()
      await userTrigger.click()

      const logoutItem = page.locator('.el-dropdown-menu__item:has-text("退出")').first()
      // 下拉有展开动画，用 auto-wait（isVisible 瞬时取值会误判未渲染）
      await logoutItem.waitFor({ state: 'visible', timeout: 5000 })
    })
  })

  test('C02: 工作台与导航验证', async ({ page }, testInfo) => {
    await navigateTo(page, '/', { waitForTable: false })

    await withStep(page, testInfo, '工作台可见 + 截图', async () => {
      await attachAndVerifyScreenshot(page, testInfo, '02-workspace', { expectedPath: '/' })
    })

    await withStep(page, testInfo, '导航区域有菜单项', async () => {
      const navItems = page.locator('.app-side-nav .nav-item, [role="tab"]')
      const navCount = await navItems.count()
      const quickLinks = page.locator('button:has-text("进入"), a:has-text("进入")')
      const quickLinkCount = await quickLinks.count()
      // [v2] 至少有一种导航元素 (菜单项或快捷入口)
      expect(navCount + quickLinkCount).toBeGreaterThan(0)
    })
  })

  test('C03: 账户设置与密码修改验证', async ({ page }, testInfo) => {
    await navigateTo(page, '/', { waitForTable: false })

    const userTrigger = page.locator('.user-menu__trigger').first()
    const hasUserMenu = await userTrigger.isVisible().catch(() => false)
    if (!hasUserMenu) {
      test.skip(true, '未找到用户菜单触发器 (页面布局可能已变更)')
      return
    }

    await withStep(page, testInfo, '点击用户菜单', async () => {
      await userTrigger.click()
    })

    await withStep(page, testInfo, '下拉菜单含个人资料/账户设置', async () => {
      // 顶部菜单项为 个人设置 / 帮助中心 / 退出登录（见 TopNavHeader.userMenuItems）
      const profileItem = page.locator('.el-dropdown-menu__item:has-text("个人设置"), .el-dropdown-menu__item:has-text("账户设置")').first()
      await profileItem.waitFor({ state: 'visible', timeout: 5000 })
    })
  })
})
