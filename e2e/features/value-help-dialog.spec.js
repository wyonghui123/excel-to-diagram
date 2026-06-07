/**
 * VHD-01: Value Help Dialog 分页验证测试
 */
import { test, expect } from '@playwright/test'
import { login, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('VHD-01: Value Help Dialog 分页验证', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await setAdminPermissions(page)
  })

  test('C01: 管理员 value help 弹窗分页验证', async ({ page }, testInfo) => {
    // 1. 导航到用户与权限页面
    await page.goto('http://localhost:3004/user-permission', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sub-nav-tabs', { timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-user-permission-page')

    // 2. 点击用户组管理 tab
    const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
    await userGroupTab.click({ force: true })
    await page.waitForTimeout(3000)

    // 3. 点击新建按钮
    await attachAndVerifyScreenshot(page, testInfo, '02-user-group-list')
    const newBtn = page.locator('.el-button:has-text("新建")').first()
    await newBtn.click({ force: true })
    await page.waitForTimeout(8000)

    await attachAndVerifyScreenshot(page, testInfo, '03-new-form')
    const currentUrl = page.url()
    console.log(`[VHD] 当前URL: ${currentUrl}`)

    // 4. 查找并点击 vh-search-icon（value help 搜索按钮）
    const searchIcons = await page.locator('.vh-search-icon').all()
    console.log(`[VHD] vh-search-icon 数量: ${searchIcons.length}`)

    if (searchIcons.length === 0) {
      // 尝试查找 value-help-field 组件
      const vhFields = await page.locator('[class*="value-help"], [class*="vh-"]').all()
      console.log(`[VHD] vh 相关元素数量: ${vhFields.length}`)
      // 截图所有可见元素用于调试
      await attachAndVerifyScreenshot(page, testInfo, '04-debug-form')
    }

    // 尝试找管理员字段的搜索按钮
    // 通常管理员字段在基本信息区域
    const adminSection = page.locator('.section-content, .form-section').filter({ hasText: /管理员/ }).first()
    if (await adminSection.isVisible({ timeout: 3000 }).catch(() => false)) {
      const sectionSearchIcon = adminSection.locator('.vh-search-icon').first()
      if (await sectionSearchIcon.isVisible({ timeout: 1000 }).catch(() => false)) {
        await sectionSearchIcon.click()
        console.log('[VHD] 点击了管理员区域搜索按钮')
      }
    }

    // 如果还没找到，尝试点击任意 vh-search-icon
    if (!await page.locator('.el-dialog').isVisible({ timeout: 2000 }).catch(() => false)) {
      const anySearchIcon = page.locator('.vh-search-icon').first()
      if (await anySearchIcon.isVisible({ timeout: 2000 }).catch(() => false)) {
        await anySearchIcon.click()
        console.log('[VHD] 点击了第一个搜索按钮')
      }
    }

    // 5. 等待弹窗
    await page.waitForSelector('.el-dialog', { timeout: 10000 })
    await page.waitForTimeout(3000)
    await attachAndVerifyScreenshot(page, testInfo, '05-dialog-opened')

    // 6. 核心验证：表格行数
    const tableRows = page.locator('.el-dialog .el-table__body tr')
    const rowCount = await tableRows.count()
    console.log(`[VHD] 表格行数: ${rowCount}`)
    expect(rowCount, `表格行数应 <= 20，实际为 ${rowCount}`).toBeLessThanOrEqual(20)
    expect(rowCount, `表格行数应 > 0，实际为 ${rowCount}`).toBeGreaterThan(0)

    // 7. 验证 max-height
    const maxHeight = await page.locator('.el-dialog .el-table').evaluate(el => getComputedStyle(el).maxHeight)
    console.log(`[VHD] max-height: ${maxHeight}`)
    expect(maxHeight, `max-height 应为 420px，实际为 ${maxHeight}`).toBe('420px')

    // 8. 验证分页信息
    const paginationText = await page.locator('.el-dialog .el-pagination').innerText().catch(() => '')
    console.log(`[VHD] 分页: ${paginationText}`)
    expect(paginationText, '分页应包含 15').toContain('15')

    // 9. 测试搜索
    const searchInput = page.locator('.el-dialog .vh-search-bar input')
    if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await searchInput.fill('admin')
      await page.waitForTimeout(800)
      await attachAndVerifyScreenshot(page, testInfo, '06-search-result')
      const filtered = await tableRows.count()
      console.log(`[VHD] 搜索后行数: ${filtered}`)
    }
  })
})
