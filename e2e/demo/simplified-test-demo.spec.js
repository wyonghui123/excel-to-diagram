/**
 * 前置工作简化 Demo - 展示新方案
 *
 * 这个文件对比：
 * - 旧版写法（每测试 5-6 行样板 + 硬编码等待）
 * - 新版写法（1 行 navigateTo + 智能 fixtures）
 *
 * 不需要真正运行 - 目的是展示代码量和可读性差异
 */

import { test, expect } from '../helpers/auto-fixtures.js'

// ============================================================
// 测试 1: 产品列表加载
// ============================================================

// [X] 旧写法（5 行样板 + 硬编码等待）
test('OLD: 产品列表加载', async ({ page }) => {
  // await login(page)  // 已通过 storageState 自动登录 - 可省略
  // await setAdminPermissions(page)  // auth.setup 已设置 - 可省略
  // await navigateAndWaitForPage(page, '/product-management', { waitForTable: true })
  // await page.waitForTimeout(1500)  // [X] 硬编码等待
  // ... 测试逻辑
  expect(true).toBe(true)  // placeholder
})

// [OK] 新写法（1 行智能导航 + 数据查找）
test('NEW: 产品列表加载', async ({ page, navigateTo, dataFinder }) => {
  await navigateTo(page, '/product-management')  // 智能导航（1 行）
  const { product } = await dataFinder.productWithVersion()  // 智能数据（1 行）

  // 直接进入测试逻辑
  expect(page.url()).toContain('product-management')
  expect(product.id).toBeTruthy()
})

// ============================================================
// 测试 2: 用户权限中心
// ============================================================

// [X] 旧写法
test('OLD: 角色管理 tab', async ({ page }) => {
  // await login(page)
  // await setAdminPermissions(page)
  // await navigateAndWaitForPage(page, '/user-permission', { waitForTabs: true })
  // await page.waitForTimeout(2000)  // [X]
  // 旧代码: 还需手动点 tab
  // const rolesTab = page.locator('text=角色管理')
  // await rolesTab.click()
  // await page.waitForTimeout(500)
  expect(true).toBe(true)
})

// [OK] 新写法
test('NEW: 角色管理 tab', async ({ page, navigateTo }) => {
  await navigateTo(page, '/user-permission', { waitForTabs: true })
  // 默认就在第一个 tab，可直接验证
  await expect(page.locator('.generic-tab-container')).toBeVisible()
})

// ============================================================
// 测试 3: 业务对象 CRUD
// ============================================================

// [X] 旧写法
test('OLD: 业务对象列表', async ({ page }) => {
  // await login(page)
  // await setAdminPermissions(page)
  // await navigateAndWaitForPage(page, '/system/archdata', { waitForTable: true })
  // await page.waitForTimeout(1500)
  expect(true).toBe(true)
})

// [OK] 新写法
test('NEW: 业务对象列表', async ({ page, navigateTo, dataFinder }) => {
  await navigateTo(page, '/system/archdata')
  const { objects } = await dataFinder.businessObject()
  expect(objects.length).toBeGreaterThan(0)
})

// ============================================================
// 测试 4: 详情页 + 数据编辑
// ============================================================

// [X] 旧写法（20+ 行样板）
test('OLD: 用户组详情编辑', async ({ page }) => {
  // await login(page)
  // await setAdminPermissions(page)
  // // 找有数据的产品/用户组
  // const groups = await getPaginatedData(page, '/api/v2/bo/user_group')
  // const group = groups.find(g => g.parent_id) || groups[0]
  // if (!group) throw new Error('no group')
  // await navigateAndWaitForPage(page, `/detail/user_group/${group.id}`, { waitForTable: true })
  // await page.waitForTimeout(1500)
  // // 找编辑按钮
  // const editBtn = page.locator('button:has-text("编辑"), button:has-text("修改")').first()
  // await editBtn.waitFor({ state: 'visible', timeout: 5000 })
  // await editBtn.click()
  // await page.waitForTimeout(1000)
  expect(true).toBe(true)
})

// [OK] 新写法（3 行就绪）
test('NEW: 用户组详情编辑', async ({ page, navigateTo, dataFinder }) => {
  const { group } = await dataFinder.userGroup({ minMembers: 0 })
  await navigateTo(page, `/detail/user_group/${group.id}`, { waitForTable: true })
  // 进入测试逻辑
  await expect(page.locator('button:has-text("编辑"), button:has-text("修改")').first()).toBeVisible()
})
