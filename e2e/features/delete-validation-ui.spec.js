/**
 * S-DVU: 删除校验 UI 通知 (盲区 5) - parametrize 风格
 *
 * 业务背景 (2026-06-12 修复回顾):
 * - 用户报"删除含成员/版本的记录时, 没看到校验失败通知"
 * - 修复: useMetaList.js 改用 ElNotification (6s, top-right) + ElMessage (3s) + console.error
 *   三重保险反馈失败
 *
 * [Phase 6 简化] (2026-06-13):
 * - 3 个 test → 1 个 describe + 3 个 parametrize
 * - 减少 ~50 行重复 (performBatchDeleteFlow 已抽, 这里再合并 3 套模板)
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 用 navigateTo() 不用 page.goto() + waitForTimeout
 * [OK] 用 dataFinder 不用硬编码 ID
 * [OK] 用 withStep 包裹步骤
 * [OK] 禁止 networkidle
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { performBatchDeleteFlow, waitForNotification, selectFirstRow } from '../helpers/delete-flow.js'

// ============================================================
// Parametrize 数据: 3 个删除校验场景
// ============================================================

const SCENARIOS = [
  {
    id: 'C01',
    name: 'product_with_versions',
    description: '删含 versions 的 product → 弹"删除失败"通知, 含"版本"',
    apiDeletePattern: '/api/v2/bo/product/batch-delete',
    navigatePath: '/product-management',
    searchTerm: (pv) => pv.product.name || pv.product.code,
    expectedTitleMatch: '删除失败',
    expectedContentMatch: /版本|子元素/,
    setupData: async (page, dataFinder) => {
      const pv = await dataFinder.productWithVersion()
      expect(pv, '需要有含 version 的 product').toBeTruthy()
      return { pv }
    }
  },
  {
    id: 'C02',
    name: 'user_group_with_members',
    description: '删含成员的 user_group → 弹"删除失败"通知, 含"成员"',
    apiDeletePattern: '/api/v2/bo/user_group/batch-delete',
    navigatePath: '/user-permission/user-groups',
    searchTerm: (ug) => ug.group.name || ug.group.code,
    expectedTitleMatch: '删除失败',
    expectedContentMatch: '成员',
    setupData: async (page, dataFinder) => {
      const ug = await dataFinder.userGroupWithMember({ createIfNone: true })
      expect(ug, '需要有含成员的 user_group').toBeTruthy()
      expect(ug.member_count, 'user_group 应有成员').toBeGreaterThanOrEqual(1)
      return { ug }
    }
  },
  {
    id: 'C03',
    name: 'product_empty_succeeds',
    description: '删无 versions 的空 product → 弹"删除成功"通知',
    apiDeletePattern: '/api/v2/bo/product/batch-delete',
    navigatePath: '/product-management',
    searchTerm: (ctx) => ctx.testId,
    expectedTitleMatch: '删除成功',
    expectedContentMatch: '成功',
    setupData: async (page, _dataFinder, isolation) => {
      // [Phase 6] 用 isolation.generateId() 替代 Date.now() 命名
      const testId = `DVU_C03_${isolation.generateId()}`
      const product = await isolation.createTracked('product', {
        code: testId,
        name: `删除校验空产品_${testId}`,
        description: 'Created by S-DVU C03 for UI notification assertion',
        is_active: true
      })
      expect(product?.id, 'product 应有 id').toBeTruthy()
      return { testId, product }
    }
  }
]

// ============================================================
// 测试套件 (parametrize)
// ============================================================

test.describe('S-DVU: 删除校验 UI 通知 (盲区 5)', () => {
  for (const scenario of SCENARIOS) {
    test(`[${scenario.id}] ${scenario.description}`, async ({
      page, navigateTo, dataFinder, isolation
    }, testInfo) => {
      // 1. 准备数据
      const ctx = await withStep(page, testInfo, '准备测试数据', async () => {
        return await scenario.setupData(page, dataFinder, isolation)
      })

      // 2. 导航到目标列表
      await withStep(page, testInfo, `导航到 ${scenario.navigatePath}`, async () => {
        await navigateTo(page, scenario.navigatePath)
      })

      // 3. 搜索目标行
      await withStep(page, testInfo, '搜索目标行', async () => {
        const search = page.locator('input[placeholder*="搜索"], input[placeholder*="名称"], input[placeholder*="编码"]').first()
        await search.fill('')
        await search.fill(scenario.searchTerm(ctx))
        await search.press('Enter')
        await page.locator('.el-table__body tr.el-table__row').first().waitFor({ state: 'visible', timeout: 10000 })
      })

      // 4. 执行删除流程
      await withStep(page, testInfo, '勾选 + 批量删除 + 确认', async () => {
        const result = await performBatchDeleteFlow(page, scenario.apiDeletePattern)
        if (result.response) {
          await testInfo.attach(`${scenario.id}-batch-delete-response`, {
            body: JSON.stringify({
              status: result.response.status(),
              body: (await result.response.text().catch(() => '')).substring(0, 500)
            }, null, 2),
            contentType: 'application/json'
          })
        }
      })

      // 5. 断言通知
      await withStep(page, testInfo, `断言 ElNotification 出现 + 文本含"${scenario.expectedContentMatch}"`, async () => {
        const notif = await waitForNotification(page)

        // 截图附件 (失败时便于排查)
        const screenshot = await page.screenshot({ fullPage: false })
        await testInfo.attach(`${scenario.id}-notification`, {
          body: screenshot,
          contentType: 'image/png'
        })

        const title = await notif.locator('.el-notification__title').textContent()
        const content = await notif.locator('.el-notification__content').textContent()

        expect(title, '通知标题').toContain(scenario.expectedTitleMatch)

        if (scenario.expectedContentMatch instanceof RegExp) {
          expect(content, '消息内容').toMatch(scenario.expectedContentMatch)
        } else {
          expect(content, '消息内容').toContain(scenario.expectedContentMatch)
        }
      })
    })
  }
})
