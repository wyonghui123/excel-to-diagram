/**
 * T13-9 冒烟：ui-meta 下发 + 枚举 batch 下发 + 列表首屏
 *
 * 覆盖三件事：
 * 1. GET /api/v1/meta/engineering_change/ui-meta 返回 list/form/detail 与 schema_version
 * 2. GET /api/v2/meta/enums/batch 返回的枚举项带 color（前端标签颜色不再本地映射）
 * 3. 工程变更列表页首屏可渲染（表格/状态筛选/查询按钮/分页）
 *
 * 规则：禁止 networkidle；认证走 helpers/auth.js；不启动 dev server。
 */
import { test, expect } from '@playwright/test'
import {
  login,
  navigateAndWaitForPage,
  setAdminPermissions
} from '../helpers/auth.js'

test.describe('T13-9 元数据下发冒烟', () => {
  test('ui-meta 与枚举 batch 契约', async ({ page }) => {
    await login(page)

    const uiMetaResp = await page.request.get('/api/v1/meta/engineering_change/ui-meta')
    expect(uiMetaResp.status()).toBe(200)
    const uiMeta = await uiMetaResp.json()
    expect(uiMeta.success).toBe(true)
    expect(uiMeta.data).toBeTruthy()
    expect(uiMeta.data.schema_version).toBeDefined()
    expect(uiMeta.data.list).toBeTruthy()
    expect(uiMeta.data.form).toBeTruthy()
    expect(uiMeta.data.detail).toBeTruthy()

    const enumResp = await page.request.get(
      '/api/v2/meta/enums/batch?names=engineering_change_status,permission_level'
    )
    expect(enumResp.status()).toBe(200)
    const enums = await enumResp.json()
    expect(enums.success).toBe(true)
    const statusItems = enums.data?.engineering_change_status || []
    expect(statusItems.length).toBeGreaterThan(0)
    expect(statusItems[0]).toMatchObject({ value: expect.any(String), label: expect.any(String) })
    expect(['success', 'warning', 'danger', 'info', 'primary']).toContain(statusItems[0].color)
  })

  test('工程变更列表首屏渲染', async ({ page }) => {
    await login(page)
    await setAdminPermissions(page)

    await navigateAndWaitForPage(page, '/master-data/engineering-change', {
      expectedPath: 'engineering-change',
      waitForTable: false
    })

    await expect(page.locator('[data-test="ec-table"]')).toBeVisible()
    await expect(page.locator('[data-test="ec-status-filter"]')).toBeVisible()
    await expect(page.locator('[data-test="ec-search"]')).toBeVisible()
    await expect(page.locator('[data-test="ec-pagination"]')).toBeVisible()

    // 首屏允许 0 行（空库），但表格/分页必须已渲染
    const errorAlert = page.locator('[data-test="ec-list-error"]')
    expect(await errorAlert.isVisible().catch(() => false)).toBe(false)
  })
})