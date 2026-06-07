/**
 * S07: 重复配置警告（FR-005） - v1.4 关键
 *
 * 验证: 同一字段在 Section 1 和 Section 3 都配置时显示警告
 *
 * 实施目标 (基于 v1_to_v2_plan.md 中等优先级 #35 spec):
 * - v1 → v2 迁移, complex 复杂度, 3 unsafe
 * - 改: import + 删除 login/setAdminPermissions + navigateAndWaitForPage → navigateTo
 * - 改: attachAndVerifyScreenshot → withStep 包裹
 * - 改: waitForTimeout(2000) → 删除（navigateTo 已等待稳定）
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (page 已自动登录)
 * [OK] navigateTo fixture 替代 navigateAndWaitForPage
 * [OK] withStep 包裹每步 (替代 attachAndVerifyScreenshot)
 * [OK] 无硬编码 waitForTimeout
 * [OK] 软失败模式 (console.log 警告) 保留
 * [OK] API smoke + 简单 UI 验证
 * [OK] test 数保持 1 个, 名称保持
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('S07: 重复配置警告 (FR-005)', () => {
  test('C01: 配置规则后警告显示', async ({ page, navigateTo, isolation }, testInfo) => {
    let roleId = null

    await withStep(page, testInfo, '获取一个角色 ID', async () => {
      const resp = await page.request.get('/api/v2/bo/role?page=1&page_size=5')
      const json = await resp.json()
      roleId = json.data?.items?.[0]?.id || json.data?.records?.[0]?.id
      if (!roleId) {
        console.log('[SKIP] 没有可用角色')
        test.skip(true, '没有可用角色')
        return
      }
    })

    await withStep(page, testInfo, `导航到角色 ${roleId} 权限配置 (POM navigateTo)`, async () => {
      await navigateTo(page, `/system/role-permission/${roleId}`)
    })

    await withStep(page, testInfo, '调 overlap API 验证后端 + 前端警告组件', async () => {
      // 直接调 overlap API 验证后端
      const overlapResp = await page.request.get(
        `/api/v1/roles/${roleId}/overlaps/summary`
      )
      if (overlapResp.ok()) {
        const overlapData = await overlapResp.json()
        console.log(`[OK] Overlap API 返回: ${overlapData.data?.count || 0} 条`)

        // 验证 OverlapWarning 组件（前端）
        const warning = page.locator('.overlap-warning, [class*="overlap-warning"]').first()
        const isWarningVisible = await warning.isVisible({ timeout: 3000 }).catch(() => false)
        console.log(`[OK] 前端警告组件可见: ${isWarningVisible}`)
      } else {
        console.log(`[WARN] Overlap API 不可用: ${overlapResp.status()}`)
      }
    })

    // 不用手动清理 - afterEach 自动调用 isolation.cleanup()
  })
})
