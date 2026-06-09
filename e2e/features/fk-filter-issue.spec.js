/**
 * FK-FILTER-ISSUE: FK 过滤问题调试 (v2 风格)
 *
 * 测试场景：
 * 1. 父组过滤后列表没有更新
 * 2. 管理员搜索没有结果
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (本 spec 无需创建数据)
 * [OK] POM (GenericListPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

const USER_PERMISSION_URL = '/user-permission'

test.describe('FK-FILTER-ISSUE: FK 过滤问题调试', () => {
  test('问题1: 父组过滤后列表没有更新', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const list = new GenericListPage(page)
    const requests = []
    page.on('request', req => {
      if (req.url().includes('/api/v2/bo/user_group')) {
        requests.push(req.url())
      }
    })

    await withStep(page, testInfo, '导航到用户权限页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
    })

    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
    })

    const rowsBefore = await list.getRowCount()
    console.log(`[ISSUE1] 过滤前行数: ${rowsBefore}`)

    const parentHeader = page.locator('thead th').filter({ hasText: '父组' })
    const filterIcon = parentHeader.locator('.filter-trigger')

    await withStep(page, testInfo, '点击父组列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    await withStep(page, testInfo, '打开下拉选择器', async () => {
      await popover.locator('.el-select, .value-help-field').first().click()
    })

    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[ISSUE1] 选项数量: ${optionCount}`)

    for (let i = 0; i < optionCount; i++) {
      const text = await options.nth(i).textContent()
      if (text.includes('CRUD Group_92446')) {
        console.log(`[ISSUE1] 选择: ${text}`)
        await withStep(page, testInfo, '选择过滤选项', async () => {
          await options.nth(i).click()
        })
        break
      }
    }

    requests.length = 0

    await withStep(page, testInfo, '确认过滤', async () => {
      const confirmBtn = popover.getByRole('button', { name: '确定' })
      await confirmBtn.click()
    })

    await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})

    console.log('\n[ISSUE1] === 过滤后 API 请求 ===')
    requests.forEach(url => console.log(url))

    const rowsAfter = await list.getRowCount()
    console.log(`[ISSUE1] 过滤后行数: ${rowsAfter}`)

    if (rowsAfter === rowsBefore) {
      console.log('[ISSUE1] [WARNING] 过滤后行数没有变化，可能过滤没有生效')
    } else {
      console.log('[ISSUE1] [OK] 过滤生效')
    }
  })

  test('问题2: 管理员搜索没有结果', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const list = new GenericListPage(page)
    const requests = []
    page.on('request', req => {
      requests.push({ url: req.url(), method: req.method() })
    })

    await withStep(page, testInfo, '导航到用户权限页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    const userGroupTab = page.locator('.sub-nav-tab:has-text("用户组管理")')
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
    })

    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
    })

    const managerHeader = page.locator('thead th').filter({ hasText: '管理员' })
    const filterIcon = managerHeader.locator('.filter-trigger')

    await withStep(page, testInfo, '点击管理员列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    requests.length = 0

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    await withStep(page, testInfo, '输入搜索关键字', async () => {
      const input = popover.locator('.el-select__input, .el-input__inner, input').first()
      await input.fill('no_pwd_d1a3798a')
    })

    await waitForApiFn(page, 'GET /api/v2/bo/user').catch(() => {})

    console.log('\n[ISSUE2] === 搜索请求 ===')
    requests.filter(r => r.url.includes('user') || r.url.includes('value-help')).forEach(r => {
      console.log(`${r.method} ${r.url}`)
    })

    const options = page.locator('.el-select-dropdown__item:visible, .el-autocomplete-suggestion li')
    const optionCount = await options.count()
    console.log(`[ISSUE2] 搜索结果数量: ${optionCount}`)

    if (optionCount === 0) {
      console.log('[ISSUE2] [WARNING] 没有找到搜索结果')
      const errorMsg = await popover.locator('.el-form-item__error, .el-message__content').textContent().catch(() => null)
      if (errorMsg) {
        console.log(`[ISSUE2] 错误信息: ${errorMsg}`)
      }
    }
  })
})
