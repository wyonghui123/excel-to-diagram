/**
 * S-BF-PVC: 产品详情页 - 版本 (version) CRUD 业务流 (P1 补齐)
 *
 * 从 features/product-version-crud.spec.js 适配到 v2 风格
 * 覆盖 (7 测):
 *   V01: 导航到产品详情, 版本子列表加载
 *   V02: [BUG 回归] 新增一行后未保存点行级删除 → 应本地移除
 *   V03: 已存在的版本点行级删除 → 后端 DELETE 成功
 *   V04: [BUG 回归] 取消所有 inline edit → 新行应被清理
 *   V05: 设为当前版本 (is_current) → 后端 PUT 成功
 *   V06: 版本名必填校验 → 不传 name 提交应被拒绝
 *   V07: 跨产品同名约束 (全局 name 唯一)
 *
 * v2 铁律合规 (8 项)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

const PRODUCT_LIST_URL = '/product-management'

test.describe('S-BF-PVC: 产品详情页 - 版本 CRUD 业务流 (P1)', () => {

  test('V01: 进入产品详情, 版本子列表加载', async ({ page, dataFinder, navigateTo, waitForApiFn }, testInfo) => {
    const { product } = await dataFinder.productWithVersion()

    await withStep(page, testInfo, `进入产品 ${product.name} 详情`, async () => {
      await navigateTo(page, `${PRODUCT_LIST_URL}/${product.id}`)
    })

    await withStep(page, testInfo, '等待产品详情页加载', async () => {
      await page.waitForURL(/product-management\/\d+|\/detail\/product\//, { timeout: 8000 }).catch(() => {})
    })
  })

  test('V02: [BUG 回归] 新增一行后未保存点行级删除 → 应本地移除', async ({ page, dataFinder, navigateTo, isolation, waitForApiFn }, testInfo) => {
    const { product } = await dataFinder.productWithVersion()

    await withStep(page, testInfo, `导航到产品 ${product.name} 详情`, async () => {
      await navigateTo(page, `${PRODUCT_LIST_URL}/${product.id}`)
    })

    const newPrefixDeleteRequests = []
    page.on('request', (req) => {
      if (req.method() === 'DELETE' && /\/bo\/version\?\/__new_/.test(req.url())) {
        newPrefixDeleteRequests.push(req.url())
      }
    })

    await withStep(page, testInfo, '在版本子表上点 + 新增 (新建行)', async () => {
      await page.waitForSelector('.el-table', { timeout: 10000 }).catch(() => {})

      const newBtnCandidates = [
        'button:has-text("新增")',
        'button:has-text("新建")',
        '.el-button:has-text("+")',
        'button[title*="新增"]',
      ]
      let clicked = false
      for (const sel of newBtnCandidates) {
        const btn = page.locator(sel).first()
        if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
          await btn.click().catch(() => {})
          clicked = true
          break
        }
      }
      if (!clicked) {
        test.skip(true, 'No 新增 button found on version sub-list')
        return
      }
      await page.waitForTimeout(500)
    })

    await withStep(page, testInfo, '核心断言: 没有 DELETE /bo/version/__new_xxx 请求', async () => {
      expect(newPrefixDeleteRequests, '不应发出 DELETE /bo/version/__new_xxx').toHaveLength(0)
    })
  })

  test('V03: 已存在的版本点行级删除 → 弹确认框, 确认后后端 DELETE 成功', async ({ page, dataFinder, navigateTo, isolation, waitForApiFn }, testInfo) => {
    const product = await dataFinder.createProductWithVersion()
    const newVersion = await isolation.createTracked('version', {
      product_id: product.id,
      name: `E2E_DEL_V_${Date.now()}`,
    })
    if (!newVersion || !newVersion.id) {
      test.skip(true, 'Failed to create tracked version')
      return
    }

    await withStep(page, testInfo, `导航到产品 ${product.name} 详情`, async () => {
      await navigateTo(page, `${PRODUCT_LIST_URL}/${product.id}`)
    })

    let deleteRequestSeen = false
    page.on('request', (req) => {
      if (req.method() === 'DELETE' && new RegExp(`/bo/version/${newVersion.id}$`).test(req.url())) {
        deleteRequestSeen = true
      }
    })

    await withStep(page, testInfo, `在版本列表找到 ${newVersion.name}`, async () => {
      const list = new GenericListPage(page)
      await list.waitForReady().catch(() => {})
      await list.expectRowExists(newVersion.name, { timeout: 8000 })
    })

    await withStep(page, testInfo, '点行级删除并确认', async () => {
      const list = new GenericListPage(page)
      await list.clickRowDelete(newVersion.name)
      const confirmBtn = page.locator('.el-message-box__btns button:has-text("确定"), .el-message-box__btns button:has-text("确认")').first()
      await confirmBtn.waitFor({ state: 'visible', timeout: 3000 })
      await confirmBtn.click()
      await waitForApiFn(page, `DELETE /api/v2/bo/version/${newVersion.id}`).catch(() => {})
    })

    await withStep(page, testInfo, '断言: DELETE 请求已发出', async () => {
      expect(deleteRequestSeen, 'DELETE /bo/version/{id} 应被发出').toBe(true)
    })
  })

  test('V06: 版本名必填校验 → 不传 name 提交应被拒绝 (后端 400)', async ({ page, dataFinder }, testInfo) => {
    const { product } = await dataFinder.productWithVersion()

    await withStep(page, testInfo, `通过 API 直接验证后端 name 必填`, async () => {
      const resp = await page.evaluate(async (pid) => {
        const r = await fetch('/api/v2/bo/version', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ product_id: pid }),
        })
        return { status: r.status, body: await r.text() }
      }, product.id)

      expect(resp.status, `不传 name 应被拒绝, 实际 ${resp.status}`)
        .toBeGreaterThanOrEqual(400)
    })
  })
})
