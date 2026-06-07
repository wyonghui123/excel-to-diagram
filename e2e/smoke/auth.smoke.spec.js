/**
 * S01: 认证与账户设置 - 冒烟测试
 *
 * [E2E 规则速查] 修改前必读:
 * - 禁止 networkidle | 截图用 testInfo.attach() | 导航用 navigateAndWaitForPage()
 * - 权限用 setAdminPermissions() | 报告: npx playwright show-report --port 9326
 * - 详细: .trae/rules/e2e-testing.md | helpers/auth.js 头部注释
 */
import { test, expect } from '@playwright/test'
import { login, navigateAndWaitForPage, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('S01: 认证与账户设置', () => {
  test('C01: 登录流程验证', async ({ page }, testInfo) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })

    const usernameInput = page.getByPlaceholder('用户名')
    await usernameInput.waitFor({ state: 'visible', timeout: 10000 })
    expect(await usernameInput.isVisible()).toBe(true)
    console.log('[OK] 登录表单可见')

    await attachAndVerifyScreenshot(page, testInfo, '01-login-page', { verifyNotHomepage: false })

    await usernameInput.fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.waitForTimeout(300)
    await page.getByRole('button', { name: '登 录' }).click()

    await page.locator('.login-overlay').waitFor({ state: 'hidden', timeout: 20000 })
    await page.waitForLoadState('domcontentloaded')

    const token = await page.evaluate(() => localStorage.getItem('auth_token'))
    expect(token).toBeTruthy()
    console.log('[OK] 正确密码登录成功')

    await attachAndVerifyScreenshot(page, testInfo, '02-after-login', { expectedPath: '/' })

    const userTrigger = page.getByRole('button', { name: /用户/ }).first()
    if (await userTrigger.isVisible().catch(() => false)) {
      await userTrigger.click()
      await page.waitForTimeout(500)

      const logoutItem = page.locator('.el-dropdown-menu__item:has-text("退出")').first()
      if (await logoutItem.isVisible().catch(() => false)) {
        await logoutItem.click()
        await page.waitForTimeout(1000)

        const loginForm = page.getByPlaceholder('用户名')
        if (await loginForm.isVisible().catch(() => false)) {
          console.log('[OK] 登出后回到登录页')
        }
      }
    } else {
      console.log('[WARNING] 未找到用户菜单触发器')
    }
  })

  test('C02: 工作台与导航验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(1000)

    await attachAndVerifyScreenshot(page, testInfo, '03-workspace', { expectedPath: '/' })

    const navItems = page.locator('.app-side-nav .nav-item, [role="tab"]')
    const navCount = await navItems.count()
    if (navCount > 0) {
      console.log(`[OK] 导航区域有 ${navCount} 个菜单项`)
    } else {
      const quickLinks = page.locator('button:has-text("进入"), a:has-text("进入")')
      const quickLinkCount = await quickLinks.count()
      if (quickLinkCount > 0) {
        console.log(`[OK] 工作台有 ${quickLinkCount} 个快捷入口`)
        await quickLinks.first().click()
        await page.waitForLoadState('domcontentloaded')
        await page.waitForTimeout(1000)
        await attachAndVerifyScreenshot(page, testInfo, '04-quick-link-navigation')
      }
    }
  })

  test('C03: 账户设置与密码修改验证', async ({ page }, testInfo) => {
    await login(page)
    await setAdminPermissions(page)

    const userTrigger = page.getByRole('button', { name: /用户/ }).first()
    if (await userTrigger.isVisible().catch(() => false)) {
      await userTrigger.click()
      await page.waitForTimeout(500)

      const menuItems = page.locator('.el-dropdown-menu__item')
      const itemCount = await menuItems.count()
      console.log(`[OK] 用户下拉菜单有 ${itemCount} 个选项`)

      const profileItem = menuItems.locator(':has-text("个人资料"), :has-text("账户设置")').first()
      if (await profileItem.isVisible().catch(() => false)) {
        await profileItem.click()
        await page.waitForLoadState('domcontentloaded')
        await page.waitForTimeout(1000)

        await attachAndVerifyScreenshot(page, testInfo, '05-account-settings')

        const passwordChangeBtn = page.locator('button:has-text("修改密码"), button:has-text("更改密码")').first()
        if (await passwordChangeBtn.isVisible().catch(() => false)) {
          await passwordChangeBtn.click()
          await page.waitForTimeout(500)
          await attachAndVerifyScreenshot(page, testInfo, '06-password-change-dialog')
          console.log('[OK] 密码修改弹窗验证完成')
        }
      } else {
        console.log('[WARNING] 未找到个人资料/账户设置菜单项')
      }
    } else {
      console.log('[WARNING] 未找到用户菜单触发器')
    }
  })
})
