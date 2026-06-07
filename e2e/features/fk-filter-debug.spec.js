/**
 * FK-FILTER-DEBUG: 调试 FK 过滤请求
 */
import { test, expect } from '@playwright/test'
import { login, setAdminPermissions } from '../helpers/auth.js'

test.describe('FK-FILTER-DEBUG: 调试 FK 过滤请求', () => {
  test('调试父组过滤请求', async ({ page }) => {
    // 监听 API 请求
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/v2/bo/user_group')) {
        requests.push({
          url: req.url(),
          method: req.method()
        })
        console.log(`[API] ${req.method()} ${req.url()}`)
      }
    })
    
    page.on('console', msg => {
      if (msg.text().includes('FilterService') || msg.text().includes('FK-FILTER')) {
        console.log(`[BROWSER] ${msg.text()}`)
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
    
    // 找到父组列的过滤图标
    const parentHeader = page.locator('.el-table__header th').filter({ hasText: '父组' })
    const filterIcon = parentHeader.locator('.filter-trigger')
    
    await filterIcon.first().click({ force: true })
    await page.waitForTimeout(500)
    
    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })
    
    // 点击下拉框
    const selectDropdown = popover.locator('.el-select, .value-help-field').first()
    await selectDropdown.click()
    await page.waitForTimeout(500)
    
    // 选择 CRUD Group_92446 选项
    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[FK-FILTER] 选项数量: ${optionCount}`)
    
    // 查找 CRUD Group_92446
    for (let i = 0; i < optionCount; i++) {
      const text = await options.nth(i).textContent()
      if (text.includes('CRUD Group_92446')) {
        console.log(`[FK-FILTER] 找到目标选项: ${text}`)
        await options.nth(i).click()
        break
      }
    }
    
    await page.waitForTimeout(500)
    
    // 清空之前的请求记录
    requests.length = 0
    
    // 点击确定按钮
    const confirmBtn = popover.locator('.el-button:has-text("确定")')
    await confirmBtn.click()
    await page.waitForTimeout(3000)
    
    // 输出所有请求
    console.log('\n=== API 请求 ===')
    for (const req of requests) {
      console.log(`${req.method} ${req.url}`)
    }
    
    // 验证过滤请求
    const filterRequest = requests.find(r => r.url.includes('parent_id'))
    if (filterRequest) {
      console.log(`\n=== 过滤请求 ===`)
      console.log(filterRequest.url)
      
      // 解析 URL 参数
      const url = new URL(filterRequest.url)
      const params = url.searchParams
      console.log('\n=== 参数 ===')
      for (const [key, value] of params.entries()) {
        console.log(`${key} = ${value}`)
      }
    } else {
      console.log('[FK-FILTER] [WARNING] 没有找到包含 parent_id 的请求')
    }
  })
})
