/**
 * M5: v1.1 owner refactor E2E 测试
 *
 * 测试场景:
 * 1. version ui-config 包含 effective_owner_id_display 列配置 (✅ C04)
 * 2. domain ui-config 包含 effective_owner_id_display 列配置 (✅ C03)
 * 3. product API 返回 effective_owner_id + owner_id (已由 M3 测试覆盖)
 * 4. 前端页面文本包含 effective_owner_id_display 值
 *
 * 注: API 测试使用 page.request (无 cookie), 需要 meta API (不需认证)
 *     UI 测试通过已登录的 page.goto 验证
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('M5: v1.1 owner refactor - effective_owner_id_display UI', () => {

  /**
   * Test C04: version ui-config 包含 effective_owner_id_display 列配置
   */
  test('C04: version ui-config 包含 effective_owner_id_display 列配置', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '获取 version ui-config', async () => {
      const resp = await page.request.get('/api/v2/meta/version/ui-config', {
        headers: { 'Accept': 'application/json' }
      })
      expect(resp.status()).toBe(200)
      const json = await resp.json()
      const cols = json.data?.ui_view_config?.list?.columns || []
      const keys = cols.map(c => c.key)
      console.log('[C04] version list columns:', keys)
      expect(keys).toContain('effective_owner_id_display')
    })
  })

  /**
   * Test C03: domain ui-config 包含 effective_owner_id_display 列配置
   */
  test('C03: domain ui-config 包含 effective_owner_id_display 列配置', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '获取 domain ui-config', async () => {
      const resp = await page.request.get('/api/v2/meta/domain/ui-config', {
        headers: { 'Accept': 'application/json' }
      })
      expect(resp.status()).toBe(200)
      const json = await resp.json()
      const cols = json.data?.ui_view_config?.list?.columns || []
      const keys = cols.map(c => c.key)
      console.log('[C03] domain list columns:', keys)
      expect(keys).toContain('effective_owner_id_display')
    })
  })

  /**
   * Test C01: 前端页面包含 effective_owner_id_display 文本 (admin Updated / test60)
   * 通过已登录的 page 对象验证前端渲染数据
   */
  test('C01: 前端 archdata 页面显示 effective_owner_id_display 文本', async ({ page }, testInfo) => {
    await withStep(page, testInfo, '登录并导航到 archdata', async () => {
      // 等待 SPA 加载
      await page.goto('/system/archdata')
      await page.waitForLoadState('domcontentloaded')
      await page.waitForTimeout(3000)
    })

    await withStep(page, testInfo, '检查页面包含 effective_owner_id_display 值', async () => {
      // 通过 document.body.textContent 验证页面渲染了 effective_owner_id_display
      // "TEST60" 是 effective_owner_id=1223 对应的 display_name
      const body = await page.evaluate(() => document.body.textContent)
      console.log('[C01] body length:', body.length)

      // 验证包含 owner display names
      const hasTest60 = body.includes('TEST60')
      const hasAdmin = body.includes('Admin Updated')
      console.log('[C01] has TEST60:', hasTest60, ', has Admin Updated:', hasAdmin)

      expect(hasTest60 || hasAdmin, '页面应包含 owner display name (TEST60 或 Admin Updated)').toBeTruthy()
    })
  })

})
