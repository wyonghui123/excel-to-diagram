/**
 * FK-FILTER-01: FK 字段过滤功能测试 (v2 风格)
 *
 * 测试场景：
 * 1. 用户组列表页父组字段过滤
 * 2. 用户组列表页管理员字段过滤
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

test.describe('FK-FILTER-01: FK 字段过滤功能', () => {
  test('C01: 用户组父组字段过滤', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到用户组页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    // 切到用户组 tab
    const userGroupTab = page.getByRole('tab', { name: '用户组管理' })
      .or(page.locator('.sub-nav-tab:has-text("用户组管理")'))
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
    })

    // 等待表格就绪
    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
    })

    const rowsBefore = await list.getRowCount()
    console.log(`[FK-FILTER] 过滤前行数: ${rowsBefore}`)

    // 找到父组列的过滤图标
    const parentHeader = page.locator('thead th').filter({ hasText: '父组' })
    const filterIcon = parentHeader.locator('.filter-trigger')

    const hasFilter = await filterIcon.count()
    console.log(`[FK-FILTER] 父组列过滤图标数量: ${hasFilter}`)
    expect(hasFilter).toBeGreaterThan(0)

    await withStep(page, testInfo, '点击父组列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    const selectDropdown = popover.locator('.el-select, .value-help-field').first()
    await expect(selectDropdown).toBeVisible({ timeout: 1000 })
    await selectDropdown.click()

    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[FK-FILTER] 选项数量: ${optionCount}`)

    if (optionCount >= 2) {
      const option = options.nth(1)
      const optionText = await option.textContent()
      console.log(`[FK-FILTER] 选择选项: ${optionText}`)

      await withStep(page, testInfo, '选择过滤选项', async () => {
        await option.click()
      })

      const confirmBtn = popover.getByRole('button', { name: '确定' })
      await withStep(page, testInfo, '确认过滤', async () => {
        await confirmBtn.click()
      })

      const rowsAfter = await list.getRowCount()
      console.log(`[FK-FILTER] 过滤后行数: ${rowsAfter}`)

      const activeFilter = page.locator('.filter-trigger.is-active')
      const activeCount = await activeFilter.count()
      console.log(`[FK-FILTER] 活跃过滤图标数量: ${activeCount}`)
      expect(activeCount).toBeGreaterThan(0)

      console.log('[FK-FILTER] 父组过滤完成')
    } else {
      console.log('[FK-FILTER] [WARN] 没有足够的选项,跳过测试')
      test.skip()
    }
  })

  test('C02: 用户组管理员字段过滤', async ({ page, navigateTo }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到用户组页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    const userGroupTab = page.getByRole('tab', { name: '用户组管理' })
      .or(page.locator('.sub-nav-tab:has-text("用户组管理")'))
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
    })

    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
    })

    const rowsBefore = await list.getRowCount()
    console.log(`[FK-FILTER] 过滤前行数: ${rowsBefore}`)

    const managerHeader = page.locator('thead th').filter({ hasText: '管理员' })
    const filterIcon = managerHeader.locator('.filter-trigger')

    const hasFilter = await filterIcon.count()
    console.log(`[FK-FILTER] 管理员列过滤图标数量: ${hasFilter}`)
    expect(hasFilter).toBeGreaterThan(0)

    await withStep(page, testInfo, '点击管理员列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    const selectDropdown = popover.locator('.el-select, .value-help-field').first()
    await expect(selectDropdown).toBeVisible({ timeout: 1000 })
    await selectDropdown.click()

    const options = page.locator('.el-select-dropdown__item:visible')
    const optionCount = await options.count()
    console.log(`[FK-FILTER] 选项数量: ${optionCount}`)

    if (optionCount >= 1) {
      const option = options.first()
      const optionText = await option.textContent()
      console.log(`[FK-FILTER] 选择选项: ${optionText}`)

      await withStep(page, testInfo, '选择过滤选项', async () => {
        await option.click()
      })

      const confirmBtn = popover.getByRole('button', { name: '确定' })
      await withStep(page, testInfo, '确认过滤', async () => {
        await confirmBtn.click()
      })

      const rowsAfter = await list.getRowCount()
      console.log(`[FK-FILTER] 过滤后行数: ${rowsAfter}`)

      const activeFilter = page.locator('.filter-trigger.is-active')
      const activeCount = await activeFilter.count()
      console.log(`[FK-FILTER] 活跃过滤图标数量: ${activeCount}`)
      expect(activeCount).toBeGreaterThan(0)

      console.log('[FK-FILTER] 管理员过滤完成')
    } else {
      console.log('[FK-FILTER] [WARN] 没有选项,跳过测试')
      test.skip()
    }
  })
})
