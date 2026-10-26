/**
 * BOM / 选配场景 - 前端 E2E
 *
 * 数据来源: meta/scripts/init_bom_scenario_seed.py（SCN- 前缀幂等种子）
 * 前置: 真实库已执行 `python -m meta.scripts.init_bom_scenario_seed`
 *
 * 覆盖:
 *   FE-01 物料结构列表加载 + 场景结构可见
 *   FE-02 销售订单详情 → 订单行 → 行操作「展开」→ 弹窗提交 → 子行落位 / 幂等提示
 *
 * v2 铁律: import 自 auto-fixtures.js / 用 navigateTo / 不用 page.goto + waitForTimeout
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

const ITEM_STRUCTURES_URL = '/item-structures'
const ORDER_NO = 'SCN-SO-BOM-1'
// 展示文本可能是物料编码或物料名称（FK 列由 value_help 决定），两种都接受
const MODEL_ITEM_TEXT = /SCN-MODEL-PC|场景模型-电脑/

async function fetchJson(page, path) {
  const resp = await page.request.get(path)
  expect(resp.ok(), `GET ${path} 应成功, 实际 ${resp.status()}`).toBe(true)
  const body = await resp.json()
  return body?.data ?? body
}

async function findScenarioOrder(page) {
  const data = await fetchJson(page, '/api/v2/bo/sales_order?page_size=200')
  const items = data?.items || []
  const order = items.find(o => o.order_no === ORDER_NO)
  expect(order, `应存在场景订单 ${ORDER_NO}（先跑种子脚本）`).toBeTruthy()
  return order
}

async function findOrderLines(page, orderId) {
  const data = await fetchJson(
    page, `/api/v2/bo/sales_order_line?order_id=${orderId}&page_size=200`)
  return data?.items || []
}

test.describe('BOM-SCN: 物料结构列表', () => {
  test('FE-01 列表加载 + 场景结构可见', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到物料结构列表', async () => {
      await navigateTo(page, ITEM_STRUCTURES_URL)
      await waitForApiFn(page, 'GET /api/v2/bo/item_structure').catch(() => {})
    })

    await withStep(page, testInfo, '表格就绪且行数 > 0', async () => {
      const table = page.locator('.el-table').first()
      await expect(table).toBeVisible()
      const rows = page.locator('.el-table__body tr')
      expect(await rows.count(), '物料结构列表应有数据').toBeGreaterThan(0)
    })

    await withStep(page, testInfo, '场景结构出现在第一页（默认 updated_at 倒序）', async () => {
      const bodyText = (await page.locator('.el-table__body').first().textContent()) || ''
      expect(
        MODEL_ITEM_TEXT.test(bodyText),
        `第一页应含场景模型结构，实际: ${bodyText.slice(0, 300)}`
      ).toBe(true)
    })
  })
})

test.describe('BOM-SCN: 销售订单行展开', () => {
  test('FE-02 行操作「展开」→ 弹窗提交 → 子行落位', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    let order
    let modelLine

    await withStep(page, testInfo, '定位场景订单与模型行', async () => {
      order = await findScenarioOrder(page)
      const lines = await findOrderLines(page, order.id)
      modelLine = lines.find(l => String(l.line_no) === '10')
      expect(modelLine, '订单应存在 10 行（SCN-MODEL-PC）').toBeTruthy()
    })

    const alreadyExpanded = modelLine.configuration_id !== null
      && modelLine.configuration_id !== undefined

    await withStep(page, testInfo, '打开订单详情并切到订单行', async () => {
      await navigateTo(page, `/detail/sales_order/${order.id}`)
      await waitForApiFn(page, `GET /api/v2/bo/sales_order/${order.id}`).catch(() => {})
      // 详情页 tabs 是 ObjectPageContent 的 .anchor-tab（非 Element Plus tabs）
      const lineTab = page.locator('.anchor-tab', { hasText: '订单行' }).first()
      await lineTab.waitFor({ state: 'visible', timeout: 10000 })
      await lineTab.click()
    })

    await withStep(page, testInfo, '行操作菜单 →「展开」', async () => {
      const row = page.locator('.el-table__body tr', { hasText: MODEL_ITEM_TEXT }).first()
      await row.waitFor({ state: 'visible', timeout: 10000 })
      await row.locator('.row-action-trigger').first().click()
      const menuItem = page.locator('.row-action-popper:visible .el-dropdown-menu__item', { hasText: '展开' }).first()
      await menuItem.waitFor({ state: 'visible', timeout: 5000 })
      await menuItem.click()
    })

    await withStep(page, testInfo, '展开弹窗出现并带父行信息', async () => {
      const dialog = page.locator('.el-dialog.sales-order-expand-dialog')
      await dialog.waitFor({ state: 'visible', timeout: 8000 })
      await expect(dialog).toContainText('展开订单行')
      await expect(dialog).toContainText('10')
    })

    await withStep(page, testInfo, '提交展开 → 成功或幂等提示', async () => {
      const rowsBefore = await page.locator('.el-table__body tr').count()
      const dialog = page.locator('.el-dialog.sales-order-expand-dialog')
      await dialog.locator('button:has-text("展开")').click()

      if (alreadyExpanded) {
        // 种子行已展开过：后端 E7 拒绝，前端须回显具体规则
        const message = page.locator('.el-message').first()
        await message.waitFor({ state: 'visible', timeout: 8000 })
        await expect(message).toContainText(/已展开|展开失败|line_already_expanded/)
        return
      }

      const message = page.locator('.el-message--success').first()
      await message.waitFor({ state: 'visible', timeout: 10000 })
      await expect(message).toContainText('已展开')
      // 详情页刷新后子行落位（10 → 3 个组件行）
      await expect.poll(
        async () => await page.locator('.el-table__body tr').count(),
        { timeout: 15000 }
      ).toBeGreaterThan(rowsBefore)
    })

    if (!alreadyExpanded) {
      await withStep(page, testInfo, '子行内容符合求解结果', async () => {
        const bodyText = (await page.locator('.el-table__body').first().textContent()) || ''
        expect(bodyText, '应出现必选组件 CPU').toMatch(/SCN-COMP-CPU|场景组件-CPU/)
        expect(bodyText, '应出现默认选项 RED').toMatch(/SCN-OPT-RED|场景选项-红色/)
        expect(bodyText, '应出现服务行 INSTALL').toMatch(/SCN-SVC-INSTALL|场景服务-上门安装/)
      })
    }
  })
})
