/**
 * M3 冒烟：列表个性化（spec §4.10）
 *
 * 覆盖：
 * 1. /product-management（page 模式）出现「列设置」，隐藏一列后表头消失
 * 2. 刷新后隐藏仍生效（localStorage 键含 schema_version）
 * 3. 「恢复默认」后列回归
 * 4. /system-admin（embedded）不出现「列设置」
 *
 * 规则：禁止 networkidle；认证走 storageState（playwright.config smoke project）。
 */
import { test, expect } from '@playwright/test'
import { navigateAndWaitForPage, setAdminPermissions } from '../helpers/auth.js'

const HEADER = '.el-table__header-wrapper th'

test.describe('M3 列表个性化冒烟', () => {
  test('page 模式：列设置隐藏列并持久化', async ({ page }) => {
    test.skip((page.viewportSize()?.width || 0) < 768, '桌面端用例')
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/product-management', { waitForTable: true })

    const settingsButton = page.getByRole('button', { name: '列设置' })
    await expect(settingsButton).toBeVisible()
    await settingsButton.click()

    const popover = page.locator('.column-settings')
    await expect(popover).toBeVisible()

    const firstItem = popover.locator('.column-settings__item .el-checkbox').first()
    const label = (await firstItem.innerText()).trim()
    await firstItem.click()
    await page.keyboard.press('Escape')

    await expect(page.locator(HEADER).filter({ hasText: label })).toHaveCount(0)

    const keys = await page.evaluate(() =>
      Object.keys(localStorage).filter(key => key.startsWith('meta-ui:list:product:'))
    )
    expect(keys.length).toBe(1)
    expect(keys[0]).toMatch(/^meta-ui:list:product:.+/)

    await page.reload()
    await page.locator('.el-table').first().waitFor({ state: 'visible' })
    await expect(page.locator(HEADER).filter({ hasText: label })).toHaveCount(0)

    await settingsButton.click()
    await popover.getByRole('button', { name: '恢复默认' }).click()
    await page.keyboard.press('Escape')
    await expect(page.locator(HEADER).filter({ hasText: label })).toHaveCount(1)
  })

  test('embedded 模式不出现列设置', async ({ page }) => {
    await setAdminPermissions(page)
    await navigateAndWaitForPage(page, '/system-admin', { waitForTable: false })
    await expect(page.getByRole('button', { name: '列设置' })).toHaveCount(0)
  })
})
