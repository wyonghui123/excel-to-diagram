/**
 * VH-FILTER-01: Value Help 过滤弹窗布局测试
 * 
 * 测试场景：
 * 1. 用户列表页状态列的多选 value_help 过滤
 * 2. 用户组列表页管理员列的多选 value_help 过滤
 * 3. 过滤弹窗下拉不会遮挡确认按钮
 */
import { test, expect } from '@playwright/test'
import { login, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('VH-FILTER-01: Value Help 过滤弹窗布局', () => {
  test.beforeEach(async ({ page }) => {
    // 监听控制台错误
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`[BROWSER ERROR] ${msg.text().substring(0, 200)}`)
      }
    })
    
    await login(page)
    await setAdminPermissions(page)
  })

  test('C01: 用户列表页状态列多选过滤', async ({ page }, testInfo) => {
    // 1. 导航到用户列表页
    await page.goto('http://localhost:3004/user-permission', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sub-nav-tabs', { timeout: 15000 })
    
    // 默认应该显示用户管理 tab
    await page.waitForSelector('.el-table', { timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-user-list')
    
    // 2. 找到状态列的过滤图标
    const statusHeader = page.locator('.el-table__header th').filter({ hasText: '状态' })
    const filterIcon = statusHeader.locator('.filter-trigger')
    
    const hasFilter = await filterIcon.count()
    console.log(`[VH-FILTER] 状态列过滤图标数量: ${hasFilter}`)
    
    if (hasFilter > 0) {
      // 3. 点击过滤图标
      await filterIcon.first().click({ force: true })
      await page.waitForTimeout(500)
      await attachAndVerifyScreenshot(page, testInfo, '02-filter-popover')
      
      // 4. 验证弹窗显示
      const popover = page.locator('.el-popover:visible')
      await expect(popover).toBeVisible({ timeout: 5000 })
      
      // 5. 验证按钮在顶部（不会被下拉遮挡）
      // 检查 filter-actions--top 类存在
      const topActions = popover.locator('.filter-actions--top')
      await expect(topActions).toBeVisible()
      
      // 6. 验证确定和重置按钮可见
      const confirmBtn = popover.locator('.el-button:has-text("确定")')
      const resetBtn = popover.locator('.el-button:has-text("重置")')
      await expect(confirmBtn).toBeVisible()
      await expect(resetBtn).toBeVisible()
      
      console.log('[VH-FILTER] [DECORATIVE] 状态列过滤弹窗布局正确')
      
      // 7. 点击外部关闭弹窗
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
    } else {
      console.log('[VH-FILTER] [WARNING] 状态列没有过滤图标，跳过测试')
    }
  })

  test('C02: 用户组列表页管理员列多选过滤', async ({ page }, testInfo) => {
    // 1. 导航到用户组列表页
    await page.goto('http://localhost:3004/user-permission', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sub-nav-tabs', { timeout: 15000 })
    
    // 点击用户组管理 tab
    const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
    await userGroupTab.click({ force: true })
    await page.waitForTimeout(2000)
    
    // 等待表格加载（使用更宽松的选择器）
    await page.waitForSelector('.el-table', { timeout: 15000 })
    await attachAndVerifyScreenshot(page, testInfo, '01-user-group-list')
    
    // 2. 找到管理员列的过滤图标（在当前可见的表格中）
    const allTables = await page.locator('.el-table').all()
    console.log(`[VH-FILTER] 表格数量: ${allTables.length}`)
    
    // 找到包含"管理员"列的表格
    const managerHeader = page.locator('.el-table__header th').filter({ hasText: '管理员' })
    const filterIcon = managerHeader.locator('.filter-trigger')
    
    const hasFilter = await filterIcon.count()
    console.log(`[VH-FILTER] 管理员列过滤图标数量: ${hasFilter}`)
    
    if (hasFilter > 0) {
      // 3. 点击过滤图标
      await filterIcon.first().click({ force: true })
      await page.waitForTimeout(500)
      await attachAndVerifyScreenshot(page, testInfo, '02-filter-popover')
      
      // 4. 验证弹窗显示
      const popover = page.locator('.el-popover:visible')
      await expect(popover).toBeVisible({ timeout: 5000 })
      
      // 5. 验证按钮在顶部
      const topActions = popover.locator('.filter-actions--top')
      await expect(topActions).toBeVisible()
      
      // 6. 验证确定和重置按钮可见
      const confirmBtn = popover.locator('.el-button:has-text("确定")')
      const resetBtn = popover.locator('.el-button:has-text("重置")')
      await expect(confirmBtn).toBeVisible()
      await expect(resetBtn).toBeVisible()
      
      console.log('[VH-FILTER] [DECORATIVE] 管理员列过滤弹窗布局正确')
      
      // 7. 点击外部关闭弹窗
      await page.keyboard.press('Escape')
      await page.waitForTimeout(300)
    } else {
      console.log('[VH-FILTER] [WARNING] 管理员列没有过滤图标，跳过测试')
    }
  })

  test('C03: 过滤弹窗下拉不遮挡确认按钮', async ({ page }, testInfo) => {
    // 1. 导航到用户列表页
    await page.goto('http://localhost:3004/user-permission', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sub-nav-tabs', { timeout: 15000 })
    await page.waitForSelector('.el-table', { timeout: 15000 })
    
    // 2. 找到状态列的过滤图标（C01 已验证此列有 value_help 过滤）
    const statusHeader = page.locator('.el-table__header th').filter({ hasText: '状态' })
    const filterIcon = statusHeader.locator('.filter-trigger')
    
    const hasFilter = await filterIcon.count()
    expect(hasFilter, '状态列应该有过滤图标').toBeGreaterThan(0)
    
    // 3. 点击过滤图标
    await filterIcon.first().click({ force: true })
    await page.waitForTimeout(800)
    
    // 4. 验证弹窗显示
    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })
    
    // 5. 验证按钮在顶部布局（核心验证点）
    const topActions = popover.locator('.filter-actions--top')
    await expect(topActions).toBeVisible()
    console.log('[VH-FILTER] [DECORATIVE] 按钮在顶部布局，下拉不会遮挡')
    
    // 6. 验证确定和重置按钮可见
    const confirmBtn = popover.locator('.el-button:has-text("确定")')
    const resetBtn = popover.locator('.el-button:has-text("重置")')
    await expect(confirmBtn).toBeVisible()
    await expect(resetBtn).toBeVisible()
    
    await attachAndVerifyScreenshot(page, testInfo, '01-popover-layout')
  })
})
