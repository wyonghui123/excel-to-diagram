/**
 * FK-FILTER-ISSUE: 调试 FK 过滤问题
 */
import { test, expect } from '@playwright/test'
import { login, setAdminPermissions } from '../helpers/auth.js'

test.describe('FK-FILTER-ISSUE: FK 过滤问题调试', () => {
  test('问题1: 父组过滤后列表没有更新', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/v2/bo/user_group')) {
        requests.push(req.url())
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
    
    // 获取过滤前的行数
    const rowsBefore = await page.locator('.el-table__row').count()
    console.log(`[ISSUE1] 过滤前行数: ${rowsBefore}`)
    
    // 点击父组过滤图标
    const parentHeader = page.locator('.el-table__header th').filter({ hasText: '父组' })
    await parentHeader.locator('.filter-trigger').first().click({ force: true })
    await page.waitForTimeout(500)
    
    // 选择 CRUD Group_92446
    const popover = page.locator('.el-popover:visible')
    await popover.locator('.el-select, .value-help-field').first().click()
    await page.waitForTimeout(500)
    
    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[ISSUE1] 选项数量: ${optionCount}`)
    
    for (let i = 0; i < optionCount; i++) {
      const text = await options.nth(i).textContent()
      if (text.includes('CRUD Group_92446')) {
        console.log(`[ISSUE1] 选择: ${text}`)
        await options.nth(i).click()
        break
      }
    }
    
    await page.waitForTimeout(300)
    
    // 清空请求记录
    requests.length = 0
    
    // 点击确定
    await popover.locator('.el-button:has-text("确定")').click()
    await page.waitForTimeout(2000)
    
    // 输出所有请求
    console.log('\n[ISSUE1] === 过滤后 API 请求 ===')
    requests.forEach(url => console.log(url))
    
    // 获取过滤后的行数
    const rowsAfter = await page.locator('.el-table__row').count()
    console.log(`[ISSUE1] 过滤后行数: ${rowsAfter}`)
    
    // 检查是否有变化
    if (rowsAfter === rowsBefore) {
      console.log('[ISSUE1] [WARNING] 过滤后行数没有变化，可能过滤没有生效')
    } else {
      console.log('[ISSUE1] [DECORATIVE] 过滤生效')
    }
  })

  test('问题2: 管理员搜索没有结果', async ({ page }) => {
    const requests = []
    page.on('request', req => {
      requests.push({ url: req.url(), method: req.method() })
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
    
    // 输入搜索关键字
    const popover = page.locator('.el-popover:visible')
    const input = popover.locator('.el-select__input, .el-input__inner, input').first()
    await input.fill('no_pwd_d1a3798a')
    await page.waitForTimeout(1500)  // 等待搜索请求
    
    // 输出所有请求
    console.log('\n[ISSUE2] === 搜索请求 ===')
    requests.filter(r => r.url.includes('user') || r.url.includes('value-help')).forEach(r => {
      console.log(`${r.method} ${r.url}`)
    })
    
    // 检查下拉选项
    const options = page.locator('.el-select-dropdown__item:visible, .el-autocomplete-suggestion li')
    const optionCount = await options.count()
    console.log(`[ISSUE2] 搜索结果数量: ${optionCount}`)
    
    if (optionCount === 0) {
      console.log('[ISSUE2] [WARNING] 没有找到搜索结果')
      
      // 检查是否有错误信息
      const errorMsg = await popover.locator('.el-form-item__error, .el-message__content').textContent().catch(() => null)
      if (errorMsg) {
        console.log(`[ISSUE2] 错误信息: ${errorMsg}`)
      }
    }
  })
})
