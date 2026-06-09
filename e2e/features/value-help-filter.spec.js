/**
 * VH-FILTER-01: Value Help 过滤弹窗布局测试 (v2 风格)
 *
 * 测试场景：
 * 1. 用户列表页状态列的多选 value_help 过滤
 * 2. 用户组列表页管理员列的多选 value_help 过滤
 * 3. 过滤弹窗下拉不会遮挡确认按钮
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码 (无测试数据创建)
 * [OK] POM (GenericListPage) 替代直接 table locator
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn 或删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (auto cleanup)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

const USER_PERMISSION_URL = '/user-permission'

test.describe('VH-FILTER-01: Value Help 过滤弹窗布局', () => {
  test('C01: 用户列表页状态列多选过滤', async ({ page, navigateTo, isolation }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到用户列表页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    await withStep(page, testInfo, '等待用户列表加载', async () => {
      await list.waitForReady()
    })

    // 找到状态列的过滤图标
    const statusHeader = page.locator('thead th').filter({ hasText: '状态' })
    const filterIcon = statusHeader.locator('.filter-trigger')

    const hasFilter = await filterIcon.count()
    console.log(`[VH-FILTER] 状态列过滤图标数量: ${hasFilter}`)

    if (hasFilter > 0) {
      await withStep(page, testInfo, '点击状态列过滤图标', async () => {
        await filterIcon.first().click({ force: true })
      })

      const popover = page.locator('.el-popover:visible')
      await expect(popover).toBeVisible({ timeout: 5000 })

      await withStep(page, testInfo, '验证按钮在顶部布局', async () => {
        const topActions = popover.locator('.filter-actions--top')
        await expect(topActions).toBeVisible()
      })

      await withStep(page, testInfo, '验证确定和重置按钮可见', async () => {
        const confirmBtn = popover.getByRole('button', { name: '确定' })
        const resetBtn = popover.getByRole('button', { name: '重置' })
        await expect(confirmBtn).toBeVisible()
        await expect(resetBtn).toBeVisible()
      })

      console.log('[VH-FILTER] 状态列过滤弹窗布局正确')

      await page.keyboard.press('Escape')
    } else {
      console.log('[VH-FILTER] [WARN] 状态列没有过滤图标，跳过测试')
    }
  })

  test('C02: 用户组列表页管理员列多选过滤', async ({ page, navigateTo, waitForApiFn, isolation }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到用户权限页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    // 切到用户组 tab
    const userGroupTab = page.getByRole('tab', { name: '用户组管理' })
      .or(page.locator('.sub-nav-tab:has-text("用户组管理")'))
    await withStep(page, testInfo, '切换到用户组管理 Tab', async () => {
      await userGroupTab.click({ force: true })
      await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
    })

    await withStep(page, testInfo, '等待用户组列表加载', async () => {
      await list.waitForReady()
      await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
    })

    // 找到管理员列的过滤图标
    const managerHeader = page.locator('thead th').filter({ hasText: '管理员' })
    const filterIcon = managerHeader.locator('.filter-trigger')

    const hasFilter = await filterIcon.count()
    console.log(`[VH-FILTER] 管理员列过滤图标数量: ${hasFilter}`)

    if (hasFilter > 0) {
      await withStep(page, testInfo, '点击管理员列过滤图标', async () => {
        await filterIcon.first().click({ force: true })
      })

      const popover = page.locator('.el-popover:visible')
      await expect(popover).toBeVisible({ timeout: 5000 })

      await withStep(page, testInfo, '验证按钮在顶部布局', async () => {
        const topActions = popover.locator('.filter-actions--top')
        await expect(topActions).toBeVisible()
      })

      await withStep(page, testInfo, '验证确定和重置按钮可见', async () => {
        const confirmBtn = popover.getByRole('button', { name: '确定' })
        const resetBtn = popover.getByRole('button', { name: '重置' })
        await expect(confirmBtn).toBeVisible()
        await expect(resetBtn).toBeVisible()
      })

      console.log('[VH-FILTER] 管理员列过滤弹窗布局正确')

      await page.keyboard.press('Escape')
    } else {
      console.log('[VH-FILTER] [WARN] 管理员列没有过滤图标，跳过测试')
    }
  })

  test('C03: 过滤弹窗下拉不遮挡确认按钮', async ({ page, navigateTo, isolation }, testInfo) => {
    const list = new GenericListPage(page)

    await withStep(page, testInfo, '导航到用户列表页', async () => {
      await navigateTo(page, USER_PERMISSION_URL)
    })

    await withStep(page, testInfo, '等待用户列表加载', async () => {
      await list.waitForReady()
    })

    // 找到状态列的过滤图标
    const statusHeader = page.locator('thead th').filter({ hasText: '状态' })
    const filterIcon = statusHeader.locator('.filter-trigger')

    const hasFilter = await filterIcon.count()
    expect(hasFilter, '状态列应该有过滤图标').toBeGreaterThan(0)

    await withStep(page, testInfo, '点击状态列过滤图标', async () => {
      await filterIcon.first().click({ force: true })
    })

    const popover = page.locator('.el-popover:visible')
    await expect(popover).toBeVisible({ timeout: 5000 })

    await withStep(page, testInfo, '验证按钮在顶部布局（核心验证点）', async () => {
      const topActions = popover.locator('.filter-actions--top')
      await expect(topActions).toBeVisible()
      console.log('[VH-FILTER] 按钮在顶部布局，下拉不会遮挡')
    })

    await withStep(page, testInfo, '验证确定和重置按钮可见', async () => {
      const confirmBtn = popover.getByRole('button', { name: '确定' })
      const resetBtn = popover.getByRole('button', { name: '重置' })
      await expect(confirmBtn).toBeVisible()
      await expect(resetBtn).toBeVisible()
    })
  })
})
