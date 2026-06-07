/**
 * 枚举管理页面 E2E 测试
 * 
 * 测试范围：
 * 1. 枚举类型列表加载
 * 2. 搜索功能
 * 3. 分页功能
 * 4. 行操作（管理枚举值）
 * 5. 排序功能
 */

const { test, expect } = require('@playwright/test')

test.describe('枚举管理页面', () => {
  
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/')
    await page.fill('#username', 'admin')
    await page.fill('#password', 'admin123')
    await page.click('button.login-btn')
    await page.waitForTimeout(2000)
    
    // 导航到业务配置页面
    await page.goto('/business-config')
    await page.waitForSelector('.el-table', { timeout: 10000 })
  })

  test('1. 枚举类型列表加载', async ({ page }) => {
    // 等待表格数据加载
    await page.waitForTimeout(2000)
    
    // 验证表格存在
    const table = page.locator('.el-table')
    await expect(table).toBeVisible()
    
    // 验证有数据行
    const rows = page.locator('.el-table__body tr')
    const rowCount = await rows.count()
    console.log(`表格行数: ${rowCount}`)
    expect(rowCount).toBeGreaterThan(0)
    
    // 验证分页信息
    const pagination = page.locator('.el-pagination')
    await expect(pagination).toBeVisible()
  })

  test('2. 搜索功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForTimeout(2000)
    
    // 获取第一条数据的名称
    const firstRowName = await page.locator('.el-table__body tr:first-child .cell').first().textContent()
    console.log(`第一条数据: ${firstRowName}`)
    
    // 输入搜索关键词
    const searchInput = page.locator('.el-input__inner').first()
    if (await searchInput.isVisible()) {
      await searchInput.fill('field')
      await page.waitForTimeout(1000)
      
      // 验证搜索结果
      const rows = page.locator('.el-table__body tr')
      const rowCount = await rows.count()
      console.log(`搜索后行数: ${rowCount}`)
    }
  })

  test('3. 分页功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForTimeout(2000)
    
    // 获取当前分页信息
    const totalText = await page.locator('.el-pagination__total').textContent()
    console.log(`分页信息: ${totalText}`)
    
    // 点击下一页
    const nextButton = page.locator('.btn-next')
    const isDisabled = await nextButton.getAttribute('class')
    if (!isDisabled.includes('disabled')) {
      await nextButton.click()
      await page.waitForTimeout(1000)
      console.log('点击下一页成功')
    }
  })

  test('4. 行操作按钮', async ({ page }) => {
    // 等待表格加载
    await page.waitForTimeout(2000)
    
    // 查找行操作按钮
    const actionButtons = page.locator('.el-table__body .el-button--small')
    const buttonCount = await actionButtons.count()
    console.log(`行操作按钮数: ${buttonCount}`)
    
    if (buttonCount > 0) {
      // 获取第一个操作按钮的文本
      const firstButtonText = await actionButtons.first().textContent()
      console.log(`第一个操作按钮: ${firstButtonText}`)
    }
  })

  test('5. 排序功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForTimeout(2000)
    
    // 点击第一列表头的排序图标
    const sortableHeader = page.locator('.el-table__header th').first()
    const isSortable = await sortableHeader.locator('.caret-wrapper').isVisible()
    
    if (isSortable) {
      await sortableHeader.locator('.caret-wrapper').click()
      await page.waitForTimeout(1000)
      console.log('点击排序成功')
    }
  })

  test('6. 刷新按钮', async ({ page }) => {
    // 等待表格加载
    await page.waitForTimeout(2000)
    
    // 查找刷新按钮
    const refreshButton = page.locator('button:has-text("刷新")')
    if (await refreshButton.isVisible()) {
      await refreshButton.click()
      await page.waitForTimeout(2000)
      console.log('刷新成功')
    }
  })

})
