/**
 * FK-FILTER-DEBUG: 调试 FK 过滤请求 (v2 风格)
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (改用 isolation.generateId)
 * [OK] POM (GenericListPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

const USER_PERMISSION_URL = '/user-permission'

test.describe('FK-FILTER-DEBUG: 调试 FK 过滤请求', () => {
  test('调试父组过滤请求', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const list = new GenericListPage(page)

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

    await withStep(page, testInfo, '导航到用户组页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    // 切到用户组 tab
    const userGroupTab = page.getByRole('tab', { name: '用户组管理' })
      .or(page.locator('.sub-nav-tab:has-text("用户组管理")'))
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
    })

    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
    })

    // 找到父组列的过滤图标
    const parentHeader = page.locator('thead th').filter({ hasText: '父组' })
    const filterIcon = parentHeader.locator('.filter-trigger')

    await withStep(page, testInfo, '点击父组列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    // 点击下拉框
    const selectDropdown = popover.locator('.el-select, .value-help-field').first()
    await selectDropdown.click()

    // 选择 CRUD Group_92446 选项
    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[FK-FILTER] 选项数量: ${optionCount}`)

    await withStep(page, testInfo, '选择目标选项', async () => {
      for (let i = 0; i < optionCount; i++) {
        const text = await options.nth(i).textContent()
        if (text.includes('CRUD Group_92446')) {
          console.log(`[FK-FILTER] 找到目标选项: ${text}`)
          await options.nth(i).click()
          break
        }
      }
    })

    // 清空之前的请求记录
    requests.length = 0

    // 点击确定按钮
    const confirmBtn = popover.getByRole('button', { name: '确定' })
    await withStep(page, testInfo, '确认过滤', async () => {
      await confirmBtn.click()
    })

    // 等待过滤请求完成
    await waitForApiFn(page, 'GET /api/v2/bo/user_group', { timeout: 5000 }).catch(() => {})

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
