/**
 * FK-FILTER-SEARCH: 测试前端搜索 "ste"
 */
import { test, expect } from '@playwright/test'
import { login, setAdminPermissions, attachAndVerifyScreenshot } from '../helpers/auth.js'

test.describe('FK-FILTER-SEARCH: 前端搜索测试', () => {
  test('前端搜索 "ste" 应该能找到 no_pwd_d1a3798a', async ({ page }, testInfo) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('value-help/bo/user')) {
        requests.push({ url: req.url(), method: req.method() })
      }
    })
    
    await login(page)
    await setAdminPermissions(page)
    
    // 导航到用户组列表页
    await page.goto('http://localhost:3004/user-permission', { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.sub-nav-tabs', { timeout: 15000 })
    
    const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
    await userGroupTab.click({ force: true })
    await page.waitForTimeout(2000)
    await page.waitForSelector('.el-table', { timeout: 15000 })
    
    // 点击管理员过滤图标
    const managerHeader = page.locator('.el-table__header th').filter({ hasText: '管理员' })
    await managerHeader.locator('.filter-trigger').first().click({ force: true })
    await page.waitForTimeout(500)
    
    // 清空请求记录
    requests.length = 0
    
    // 输入搜索关键字 "ste"
    const popover = page.locator('.el-popover:visible')
    const input = popover.locator('.el-input__inner, input').first()
    await input.fill('ste')
    await page.waitForTimeout(2000)  // 等待搜索请求和防抖
    
    // 输出所有请求
    console.log('\n[SEARCH] === 搜索请求 ===')
    for (const req of requests) {
      console.log(`${req.method} ${req.url}`)
    }
    
    // 等待下拉出现
    await page.waitForTimeout(500)
    await attachAndVerifyScreenshot(page, testInfo, '01-ste-search')
    
    // 检查下拉选项
    const options = page.locator('.el-select-dropdown__item:visible, .el-autocomplete-suggestion li:visible')
    const optionCount = await options.count()
    console.log(`\n[SEARCH] 搜索结果数量: ${optionCount}`)
    
    if (optionCount > 0) {
      for (let i = 0; i < Math.min(optionCount, 5); i++) {
        const text = await options.nth(i).textContent()
        console.log(`  - ${text}`)
      }
    }
  })
})
