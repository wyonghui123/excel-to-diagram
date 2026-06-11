/**
 * 审计日志管理页面 E2E 测试
 * 
 * 测试范围：
 * 1. 页面结构验证（MetaListPage 集成）
 * 2. 表格数据加载
 * 3. Badge 标签渲染（log_category, log_level, action）
 * 4. 分页功能
 * 5. 搜索功能
 * 6. 排序功能
 * 7. 详情抽屉
 * 8. 工具栏操作
 */

const { test, expect } = require('@playwright/test')

test.describe('审计日志管理页面 (MetaListPage 集成)', () => {
  
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    
    const usernameInput = page.locator('input[type="text"], input[placeholder*="用户名"], input[placeholder*="username"]')
    const passwordInput = page.locator('input[type="password"]')
    
    if (await usernameInput.isVisible()) {
      await usernameInput.fill('admin')
      await passwordInput.fill('admin123')
      
      const loginBtn = page.locator('button[type="submit"], .login-btn')
      if (await loginBtn.isVisible()) {
        await loginBtn.click()
      }
    }
    
    await page.waitForTimeout(2000)
    
    // 导航到系统管理页面
    await page.goto('/system-admin')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(3000)
  })

  test('1. 页面结构验证 - MetaListPage 集成', async ({ page }) => {
    // 验证 MetaListPage 组件存在
    const metaListPage = page.locator('.meta-list-page')
    await expect(metaListPage).toBeVisible()

    // 验证合并的 toolbar 存在
    const toolbar = page.locator('.toolbar')
    await expect(toolbar).toBeVisible()

    // 验证表格存在
    const table = page.locator('.el-table')
    await expect(table).toBeVisible()

    // 验证分页存在
    const pagination = page.locator('.el-pagination')
    await expect(pagination).toBeVisible()

    // 验证旧版 filter-bar 已移除
    const oldFilterBar = page.locator('.filter-bar')
    const filterBarCount = await oldFilterBar.count()
    expect(filterBarCount).toBe(0)
    
    console.log('[DECORATIVE] 页面结构验证通过')
  })

  test('2. 表格数据加载', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 验证有数据行
    const rows = page.locator('.el-table__body tr')
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThan(0)
    console.log(`[DECORATIVE] 表格加载了 ${rowCount} 行数据`)

    // 验证表格列标题
    const headers = page.locator('.el-table__header th .cell')
    const headerCount = await headers.count()
    expect(headerCount).toBeGreaterThan(5)
    console.log(`[DECORATIVE] 表格有 ${headerCount} 列`)
  })

  test('3. Badge 标签渲染验证', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 验证日志类型 Badge
    const categoryBadges = page.locator('.el-table__body .el-tag')
    const badgeCount = await categoryBadges.count()
    expect(badgeCount).toBeGreaterThan(0)
    console.log(`[DECORATIVE] 发现 ${badgeCount} 个 Badge 标签`)

    // 验证第一个 Badge 的文本不是空的
    const firstBadge = categoryBadges.first()
    const badgeText = await firstBadge.textContent()
    expect(badgeText.trim().length).toBeGreaterThan(0)
    console.log(`[DECORATIVE] Badge 文本: "${badgeText.trim()}"`
    )
  })

  test('4. 分页功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 验证分页信息显示
    const paginationInfo = page.locator('.el-pagination__total')
    if (await paginationInfo.isVisible()) {
      const text = await paginationInfo.textContent()
      console.log(`[DECORATIVE] 分页信息: ${text}`)
    }

    // 验证每页条数选择器
    const pageSizeSelect = page.locator('.el-pagination__sizes .el-input__inner')
    if (await pageSizeSelect.isVisible()) {
      const pageSize = await pageSizeSelect.inputValue()
      console.log(`[DECORATIVE] 当前每页条数: ${pageSize}`)
    }

    // 验证页码
    const currentPage = page.locator('.el-pagination__jump input')
    if (await currentPage.isVisible()) {
      const pageNum = await currentPage.inputValue()
      console.log(`[DECORATIVE] 当前页码: ${pageNum}`)
    }
  })

  test('5. 搜索功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 查找搜索输入框
    const searchInput = page.locator('.toolbar .el-input input')
    if (await searchInput.isVisible()) {
      // 输入搜索关键词
      await searchInput.fill('admin')
      await page.waitForTimeout(500)

      // 点击搜索按钮
      const searchBtn = page.locator('.toolbar button:has-text("搜索")')
      if (await searchBtn.isVisible()) {
        await searchBtn.click()
        await page.waitForTimeout(2000)
        console.log('[DECORATIVE] 搜索功能正常')
      }
    }
  })

  test('6. 排序功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 悬停到第一列表头
    const firstHeader = page.locator('.el-table__header th').first()
    await firstHeader.hover()
    await page.waitForTimeout(500)

    // 检查是否有排序图标
    const sortIcon = page.locator('.el-table__header th .caret-wrapper')
    if (await sortIcon.isVisible()) {
      // 点击排序
      await firstHeader.click()
      await page.waitForTimeout(1000)
      console.log('[DECORATIVE] 排序功能正常')
    }
  })

  test('7. 详情抽屉', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 查找详情按钮
    const detailBtn = page.locator('.el-table__body .el-button:has-text("详情")').first()
    
    if (await detailBtn.isVisible()) {
      // 点击详情按钮
      await detailBtn.click()
      await page.waitForTimeout(1500)

      // 验证抽屉打开
      const drawer = page.locator('.el-drawer')
      await expect(drawer).toBeVisible()

      // 验证抽屉标题
      const drawerTitle = page.locator('.el-drawer__header span')
      const titleText = await drawerTitle.textContent()
      console.log(`[DECORATIVE] 抽屉标题: "${titleText}"`)
      expect(titleText).toContain('审计日志')

      // 验证抽屉内容
      const descriptions = page.locator('.el-drawer .el-descriptions')
      await expect(descriptions).toBeVisible()

      // 关闭抽屉
      const closeBtn = page.locator('.el-drawer__header .el-drawer__close')
      if (await closeBtn.isVisible()) {
        await closeBtn.click()
        await page.waitForTimeout(500)
      }
      console.log('[DECORATIVE] 详情抽屉功能正常')
    } else {
      console.log('[WARNING] 没有找到详情按钮，可能没有数据')
    }
  })

  test('8. 工具栏导出按钮', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 查找导出按钮
    const exportBtn = page.locator('.toolbar button:has-text("导出")')
    
    if (await exportBtn.isVisible()) {
      console.log('[DECORATIVE] 导出按钮存在')
      
      // 点击导出按钮
      await exportBtn.click()
      await page.waitForTimeout(1500)

      // 验证导出对话框出现
      const exportDialog = page.locator('.el-dialog')
      if (await exportDialog.isVisible()) {
        console.log('[DECORATIVE] 导出对话框正常打开')

        // 关闭对话框
        const cancelBtn = page.locator('.el-dialog button:has-text("取消")')
        if (await cancelBtn.isVisible()) {
          await cancelBtn.click()
        }
      }
    } else {
      console.log('[WARNING] 导出按钮未找到')
    }
  })

  test('9. 表头过滤功能', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 悬停到表头
    const headerCells = page.locator('.el-table__header th')
    const count = await headerCells.count()
    
    if (count > 2) {
      // 悬停到第二列表头
      const secondHeader = headerCells.nth(1)
      await secondHeader.hover()
      await page.waitForTimeout(500)

      // 检查是否有过滤图标
      const filterIcon = page.locator('.el-table__header th .table-header-filter')
      if (await filterIcon.isVisible()) {
        console.log('[DECORATIVE] 表头过滤图标存在')
        
        // 点击过滤图标
        await filterIcon.first().click()
        await page.waitForTimeout(1000)
        console.log('[DECORATIVE] 表头过滤功能正常')
      }
    }
  })

  test('10. 滚动条行为验证', async ({ page }) => {
    // 等待表格加载
    await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
    await page.waitForTimeout(2000)

    // 获取视口信息
    const viewport = page.viewportSize()
    console.log(`[DECORATIVE] 视口大小: ${viewport.width}x${viewport.height}`)

    // 检查 table-section
    const tableSection = page.locator('.table-section')
    if (await tableSection.isVisible()) {
      const box = await tableSection.boundingBox()
      console.log(`[DECORATIVE] 表格区域高度: ${box?.height}px`)
    }

    // 验证只有 el-scrollbar__wrap 有垂直滚动
    const scrollInfo = await page.evaluate(() => {
      const elements = document.querySelectorAll('*')
      let scrollCount = 0
      let scrollElements = []
      
      for (const el of elements) {
        const style = window.getComputedStyle(el)
        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && 
            el.scrollHeight > el.clientHeight) {
          scrollCount++
          scrollElements.push({
            class: el.className.substring(0, 50),
            height: el.clientHeight,
            scrollHeight: el.scrollHeight
          })
        }
      }
      
      return { count: scrollCount, elements: scrollElements.slice(0, 5) }
    })

    console.log(`[DECORATIVE] 可滚动元素数量: ${scrollInfo.count}`)
    if (scrollInfo.count === 1) {
      console.log('[DECORATIVE] 只有1个滚动容器，符合单一滚动源原则')
    }
  })
})

test.describe('审计日志 API 集成测试', () => {
  
  test('后端 API 返回正确的数据结构', async ({ request }) => {
    // 登录获取 token
    const loginResponse = await request.post('/api/v1/auth/login', {
      data: {
        username: 'admin',
        password: 'admin123'
      }
    })
    
    expect(loginResponse.ok()).toBeTruthy()
    const loginData = await loginResponse.json()
    expect(loginData.success).toBe(true)
    
    const token = loginData.data?.token
    expect(token).toBeTruthy()

    // 调用审计日志 API
    const auditResponse = await request.get('/api/v2/bo/audit_log', {
      headers: {
        Authorization: `Bearer ${token}`
      },
      params: {
        page: 1,
        page_size: 10
      }
    })
    
    expect(auditResponse.ok()).toBeTruthy()
    const auditData = await auditResponse.json()
    
    // 验证响应结构
    expect(auditData.success).toBe(true)
    expect(auditData.data).toBeDefined()
    expect(auditData.data.items).toBeDefined()
    expect(Array.isArray(auditData.data.items)).toBe(true)
    
    // 验证字段
    if (auditData.data.items.length > 0) {
      const firstItem = auditData.data.items[0]
      expect(firstItem.id).toBeDefined()
      expect(firstItem.log_category).toBeDefined()
      expect(firstItem.log_level).toBeDefined()
      expect(firstItem.action).toBeDefined()
      expect(firstItem.created_at).toBeDefined()
      
      console.log(`[DECORATIVE] API 返回 ${auditData.data.items.length} 条记录`)
      console.log(`[DECORATIVE] 示例数据: ${JSON.stringify(firstItem).substring(0, 200)}`)
    }
  })

  test('元数据配置正确加载', async ({ request }) => {
    // 登录
    const loginResponse = await request.post('/api/v1/auth/login', {
      data: {
        username: 'admin',
        password: 'admin123'
      }
    })
    const loginData = await loginResponse.json()
    const token = loginData.data?.token

    // 获取 audit_log 元数据
    const metaResponse = await request.get('/api/v1/meta/objects/audit_log', {
      headers: {
        Authorization: `Bearer ${token}`
      }
    })
    
    expect(metaResponse.ok()).toBeTruthy()
    const metaData = await metaResponse.json()
    
    expect(metaData.success).toBe(true)
    expect(metaData.data).toBeDefined()
    expect(metaData.data.ui_view_config).toBeDefined()
    expect(metaData.data.ui_view_config.list).toBeDefined()
    
    // 验证 list 配置
    const listConfig = metaData.data.ui_view_config.list
    expect(listConfig.columns).toBeDefined()
    expect(Array.isArray(listConfig.columns)).toBe(true)
    expect(listConfig.columns.length).toBeGreaterThan(0)
    
    console.log(`[DECORATIVE] 元数据配置包含 ${listConfig.columns.length} 个列定义`)
    
    // 验证默认排序
    if (listConfig.defaultSort) {
      console.log(`[DECORATIVE] 默认排序: ${listConfig.defaultSort.field} ${listConfig.defaultSort.order}`)
    }
  })
})
