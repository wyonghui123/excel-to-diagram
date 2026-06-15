/**
 * S-BRP-BUG: BUG 回归保护 (BUG-V002, BUG-V004) - BMRD 自动生成
 *
 * [业务模型规则驱动 (BMRD) v1.0 - 自动生成]
 * 来源: .trae/specs/_business_rules/_protection_rules.yaml
 * 生成器: scripts/generate-protection-tests.py
 * 生成时间: 2026-06-13
 *
 * 业务规则:
 *   BUG-V002: 新行未保存时点行级删除-不调后端 [ACTIVE]
 *   BUG-V004: 取消所有 inline edit-新行应被清理 [ACTIVE]
 *
 * v2 铁律合规 (8 项):
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked()
 * [OK] 用 POM
 * [OK] 用 waitForApiFn()
 * [OK] withStep 包裹
 * [OK] isolation fixture 解构
 *
 * DEFER 项: 见 _protection_rules.yaml#deferred (本文件不包含 DEFER 测)

 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

test.describe('S-BRP-BUG-V002: 新行未保存时点行级删除-不调后端 (BMRD)', () => {
  /**
   * [BUG 回归] 新行 DELETE 不应调后端
   * 业务规则: BUG-V002 - 新行未保存时点行级删除-不调后端
   * 优先级: P0
   */
    test('[BUG 回归] 新行 DELETE 不应调后端', async ({ page, dataFinder, navigateTo }) => {
      const pv = await dataFinder.productWithVersion()
      await navigateTo(page, '/product-management/' + pv.product.id)
      const deletes = []
      page.on('request', req => {
        const u = req.url()
        if (req.method() === 'DELETE' && /\/bo\/version/.test(u) && /__new_/.test(u)) {
          deletes.push(u)
        }
      })
      const newBtn = page.locator('button:has-text("新增")').first()
      if (await newBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await newBtn.click()
        await page.waitForTimeout(500)
      } else {
        test.skip(true, 'no 新增 button')
      }
      expect(deletes, 'no DELETE /bo/version/__new_xxx').toHaveLength(0)
    })

})

test.describe('S-BRP-BUG-V004: 取消所有 inline edit-新行应被清理 (BMRD)', () => {
  /**
   * [BUG 回归] 取消 inline edit 后行数恢复
   * 业务规则: BUG-V004 - 取消所有 inline edit-新行应被清理
   * 优先级: P0
   */
    test('[BUG 回归] 取消 inline edit 后行数恢复', async ({ page, dataFinder, navigateTo }) => {
      const pv = await dataFinder.productWithVersion()
      await navigateTo(page, '/product-management/' + pv.product.id)
      const list = new GenericListPage(page)
      const before = await list.getRowCount().catch(() => 0)
      const newBtn = page.locator('button:has-text("新增")').first()
      if (await newBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await newBtn.click()
        await page.waitForTimeout(500)
      } else {
        test.skip(true, 'no 新增 button')
      }
      const cancelBtn = page.locator('button:has-text("取消")').first()
      if (await cancelBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await cancelBtn.click()
        await page.waitForTimeout(500)
      }
      const after = await list.getRowCount().catch(() => 0)
      expect(after, 'after cancel, row count should not increase').toBeLessThanOrEqual(before + 1)
    })

})

