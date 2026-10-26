/**
 * 销售订单波次场景 - 前端 E2E
 *
 * 数据来源: meta/scripts/init_sales_order_scenario_seed.py（SCN-SO- 前缀幂等种子）
 * 前置: 真实库已执行 `python -m meta.scripts.init_sales_order_scenario_seed`
 *
 * 覆盖:
 *   FE-01 列表页搜索 + 场景订单可见（含抬头金额）
 *   FE-02 W0 详情：抬头汇总 / 行金额（行级舍入）在 UI 正确展示
 *   FE-03 W0 退货单：整行金额取负
 *   FE-04 W2-D 已确认单：状态标签 + 收货地址引用展示
 *   FE-05 W1-A 重新取价端点 → 详情行单价回落 UI（74.16）
 *   FE-06 W0 冻结：已确认单改币种被拒 / 删行被拒（规则码断言）
 *   FE-07 W1-B/C/D 新建订单默认带出（组织段覆盖 → 账户级回退 → 停用忽略 → 全空）
 *   FE-08 W2-A 服务行默认值只补空（4 项默认值 / 已填不覆盖）
 *   FE-09 W1-A 取价失败码（NO_CANDIDATE / CURRENCY_MISMATCH）+ 手工价保护
 *   FE-10 销售单位默认：行不填单位 → 取物料销售单位 / 显式单位不被覆盖 / 无销售单位回落基本单位
 *   FE-11 W1-A 新建订单自动取价（price_source=rate_table + 抬头 determined）
 *   FE-12 W1-A 取价轨迹回放（无 explain 端点，用行 price_trace 替代）
 *   FE-13 W0 确认后改行数量被守卫拦截（W1-R7）
 *   FE-14 W2-A 服务属性反例（goods 行填服务列 / 停用服务物料）
 *   FE-15 W2-D 确认时地址文本快照 + 离草稿只读
 *
 * v2 铁律: import 自 auto-fixtures.js / 用 navigateTo / 不用 page.goto + waitForTimeout
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

const LIST_URL = '/sales-orders'
const ORDER_W0 = 'SCN-SO-W0-1'
const ORDER_RET = 'SCN-SO-W0-RET-1'
const ORDER_CONF = 'SCN-SO-W2-CONF-1'
const ORDER_PRICE = 'SCN-SO-W1-PRICE-1'
const ORDER_NOCAND = 'SCN-SO-W1-NOCAND-1'
const ORDER_CCY = 'SCN-SO-W1-CCY-1'
const ORDER_MANUAL = 'SCN-SO-W1-MANUAL-1'
const ORDER_SVC = 'SCN-SO-W2-SVC-1'
const ORDER_ADDR = 'SCN-SO-W9-E2E-ADDR-1'
const ADDR_SHIP = 6
const ADDR_BILL = 7

const ORG_EAST = 318          // 华东销售中心（org_functions.function_type='sales'）
const ORDER_TYPE_STD = 1      // TA 标准销售订单
const LINE_TYPE_STD = 101     // STD
const LINE_TYPE_SVC = 102     // SVC
const TAX_13 = 1              // CN_VAT_13
const TAX_6 = 3               // CN_VAT_6
const UOM_FEA = 2             // 前端验证单位

// FK 列展示文本可能是编码或名称，两种都接受
const ITEM_CPU = /SCN-SO-ITEM-CPU|场景组件-CPU/
const ITEM_BIKE = /SCN-SO-ITEM-BIKE|场景成品-自行车/

async function fetchJson(page, path) {
  const resp = await page.request.get(path)
  expect(resp.ok(), `GET ${path} 应成功, 实际 ${resp.status()}`).toBe(true)
  const body = await resp.json()
  return body?.data ?? body
}

async function findOrder(page, orderNo) {
  const data = await fetchJson(page, '/api/v2/bo/sales_order?page_size=200')
  const items = data?.items || []
  const order = items.find(o => o.order_no === orderNo)
  expect(order, `应存在场景订单 ${orderNo}（先跑种子脚本）`).toBeTruthy()
  return order
}

async function findOrderOrNull(page, orderNo) {
  const data = await fetchJson(page, '/api/v2/bo/sales_order?page_size=200')
  return (data?.items || []).find(o => o.order_no === orderNo) || null
}

async function openDetail(page, navigateTo, waitForApiFn, order, testInfo) {
  await withStep(page, testInfo, `打开订单 ${order.order_no} 详情`, async () => {
    await navigateTo(page, `/detail/sales_order/${order.id}`)
    await waitForApiFn(page, `GET /api/v2/bo/sales_order/${order.id}`).catch(() => {})
  })
}

async function openLineTab(page, testInfo, expectedText) {
  await withStep(page, testInfo, '切到订单行', async () => {
    const tab = page.locator('.anchor-tab', { hasText: '订单行' }).first()
    await tab.waitFor({ state: 'visible', timeout: 10000 })
    await tab.click()
    // 子表按父键 order_id 过滤取数，等目标行内容落位（而非只等首行），
    // 避免统计到过滤生效前的全量中间态
    await expect(page.locator('.el-table__body').first())
      .toContainText(expectedText, { timeout: 15000 })
  })
}

// ---- API 直连辅助（创建 / 回读 / 清理） ----

const blankToNull = v => (v === undefined || v === '' ? null : v)

async function listBo(page, type) {
  const data = await fetchJson(page, `/api/v2/bo/${type}?page_size=200`)
  return data?.items || []
}

async function findByField(page, type, field, value) {
  const rows = await listBo(page, type)
  const hit = rows.find(r => String(r[field]) === String(value))
  expect(hit, `应存在 ${type}.${field}=${value}（先跑种子脚本）`).toBeTruthy()
  return hit
}

async function createBo(page, type, payload) {
  const resp = await page.request.post(`/api/v2/bo/${type}`, { data: payload })
  const text = await resp.text()
  expect(resp.status(), `创建 ${type} 应 201，实际 ${resp.status()}：${text}`).toBe(201)
  const body = JSON.parse(text)
  expect(body.success, body.message || '').toBe(true)
  return body.data
}

async function readBo(page, type, id) {
  return fetchJson(page, `/api/v2/bo/${type}/${id}`)
}

async function dropBo(page, type, id) {
  const resp = await page.request.delete(`/api/v2/bo/${type}/${id}`)
  if (!resp.ok()) {
    console.warn(`[cleanup] 删除 ${type}/${id} 失败：${resp.status()}`)
  }
}

async function fetchOrderLines(page, orderId) {
  const data = await fetchJson(
    page, `/api/v2/bo/sales_order_line?order_id=${orderId}&page_size=100`)
  return data?.items || []
}

test.describe('SO-SCN: 列表', () => {
  test('FE-01 搜索场景订单并展示抬头金额', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    await withStep(page, testInfo, '导航到销售订单列表', async () => {
      await navigateTo(page, LIST_URL)
      await waitForApiFn(page, 'GET /api/v2/bo/sales_order').catch(() => {})
    })

    await withStep(page, testInfo, '按单号搜索', async () => {
      const input = page.locator('.search-field input').first()
      await input.waitFor({ state: 'visible', timeout: 10000 })
      await input.fill(ORDER_W0)
      await input.press('Enter')
      await waitForApiFn(page, 'GET /api/v2/bo/sales_order').catch(() => {})
    })

    await withStep(page, testInfo, '场景订单行可见且金额正确', async () => {
      const body = page.locator('.el-table__body').first()
      await expect(body).toContainText(ORDER_W0, { timeout: 10000 })
      const text = (await body.textContent()) || ''
      expect(text, '抬头含税金额应为 382.32').toMatch(/382\.32/)
      expect(text, '草稿状态标签应可见').toContain('草稿')
    })
  })
})

test.describe('SO-SCN: 详情', () => {
  test('FE-02 W0 抬头汇总与行级舍入', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const order = await findOrder(page, ORDER_W0)
    await openDetail(page, navigateTo, waitForApiFn, order, testInfo)

    await withStep(page, testInfo, '抬头金额 = 行合计', async () => {
      const text = (await page.locator('.object-page-content, .meta-object-page, body')
        .first().textContent()) || ''
      expect(text, '净额 338.34').toMatch(/338\.34/)
      expect(text, '税额 43.98').toMatch(/43\.98/)
      expect(text, '含税 382.32').toMatch(/382\.32/)
    })

    await openLineTab(page, testInfo, ITEM_CPU)

    await withStep(page, testInfo, '3 行落位且行级先舍入', async () => {
      const rows = page.locator('.el-table__body tr')
      await expect(rows, '订单应含 3 行').toHaveCount(3, { timeout: 10000 })
      const text = (await page.locator('.el-table__body').first().textContent()) || ''
      expect(text).toMatch(ITEM_CPU)
      expect(text).toMatch(ITEM_BIKE)
      // 300×13% = 39；13.335 → 行净额 13.34 / 税额 1.73 / 含税 15.07
      expect(text, '行 10 含税 339').toMatch(/339(\.00)?/)
      expect(text, '行 30 含税 15.07').toMatch(/15\.07/)
    })
  })

  test('FE-03 W0 退货单金额取负', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const order = await findOrder(page, ORDER_RET)
    await openDetail(page, navigateTo, waitForApiFn, order, testInfo)

    await withStep(page, testInfo, '抬头金额为负', async () => {
      const text = (await page.locator('.object-page-content, .meta-object-page, body')
        .first().textContent()) || ''
      expect(text).toMatch(/-100(\.00)?/)
      expect(text).toMatch(/-13(\.00)?/)
      expect(text).toMatch(/-113(\.00)?/)
    })

    await openLineTab(page, testInfo, /-113(\.00)?/)
  })

  test('FE-04 已确认单状态与收货地址', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const order = await findOrder(page, ORDER_CONF)
    await openDetail(page, navigateTo, waitForApiFn, order, testInfo)

    const address = await fetchJson(page, '/api/v2/bo/address/6')
    const addressText = address?.formatted_address
    expect(addressText, '地址 6 应有 formatted_address').toBeTruthy()

    await withStep(page, testInfo, '状态标签为已确认', async () => {
      const text = (await page.locator('.object-page-content, .meta-object-page, body')
        .first().textContent()) || ''
      expect(text).toContain('已确认')
    })

    await withStep(page, testInfo, '收货地址引用展示', async () => {
      const text = (await page.locator('.object-page-content, .meta-object-page, body')
        .first().textContent()) || ''
      expect(text).toContain(addressText)
    })
  })

  test('FE-05 重新取价后单价回落详情', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const order = await findOrder(page, ORDER_PRICE)

    await withStep(page, testInfo, '调用重新取价端点', async () => {
      const resp = await page.request.post(
        `/api/v1/sales-orders/${order.id}/reprice`)
      expect(resp.ok(), `POST reprice 应成功, 实际 ${resp.status()}`).toBe(true)
      const body = await resp.json()
      const data = body?.data ?? body
      expect(data?.repriced, '至少重取 1 行').toBeGreaterThan(0)
      expect(data?.pricing_status, '抬头定价状态应为已取价').toBe('determined')
    })

    await withStep(page, testInfo, '行取价来源复位为价目表', async () => {
      const lines = await fetchOrderLines(page, order.id)
      const priced = lines.find(l => blankToNull(l.unit_price) !== null)
      expect(priced, '应存在已取价行').toBeTruthy()
      expect(priced.price_source, '重取后来源应为 rate_table').toBe('rate_table')
    })

    await openDetail(page, navigateTo, waitForApiFn, order, testInfo)
    await openLineTab(page, testInfo, /74\.16/)

    await withStep(page, testInfo, '行单价展示为 74.16', async () => {
      const text = (await page.locator('.el-table__body').first().textContent()) || ''
      // 客户价 80 → 10% 折扣 → 3% 附加费 = 74.16
      expect(text).toMatch(/74\.16/)
    })
  })

  test('FE-06 W0 已确认单冻结字段与禁删行', async ({ page }, testInfo) => {
    const order = await findOrder(page, ORDER_CONF)

    await withStep(page, testInfo, '已确认单改币种被拒', async () => {
      const resp = await page.request.put(
        `/api/v2/bo/sales_order/${order.id}`, { data: { currency_id: 9 } })
      expect(resp.status(), '已确认单改币种应 400').toBe(400)
      const body = await resp.json()
      expect(body.success).toBe(false)
      expect(body.errors?.[0]?.rule, '应命中冻结规则')
        .toBe('field_frozen_after_draft')
    })

    await withStep(page, testInfo, '币种未被改动', async () => {
      const fresh = await readBo(page, 'sales_order', order.id)
      expect(Number(fresh.currency_id), '币种仍为 CNY(8)').toBe(8)
    })

    await withStep(page, testInfo, '已确认单删行被拒', async () => {
      const lines = await fetchOrderLines(page, order.id)
      expect(lines.length, '已确认单应至少有 1 行').toBeGreaterThan(0)
      const resp = await page.request.delete(
        `/api/v2/bo/sales_order_line/${lines[0].id}`)
      expect(resp.status(), '已确认单删行应 400').toBe(400)
      const body = await resp.json()
      expect(body.errors?.[0]?.rule, '应命中禁删行规则')
        .toBe('line_delete_parent_not_draft')
    })
  })
})

test.describe('SO-SCN: 默认值解析', () => {
  test('FE-07 W1-B/C/D 新建订单默认带出', async ({ page }, testInfo) => {
    const cust = {}
    for (const key of ['A', 'B', 'C', 'D']) {
      cust[key] = await findByField(
        page, 'customer_account', 'name', `SCN-SO-客户${key}`)
    }
    const sp1 = await findByField(page, 'salesperson', 'code', 'SCN-SO-SP-1')
    const sp2 = await findByField(page, 'salesperson', 'code', 'SCN-SO-SP-2')

    const stamp = Date.now().toString().slice(-6)
    const cases = [
      // 组织段逐字段覆盖 + 双地址 + 通用主销售员
      { key: 'A', payment: 1, incoterm: 'FOB', ship: 6, bill: 7, sp: sp1.id },
      // 无组织行 → 账户级回退；只有收货地址；组织专属销售员优先
      { key: 'B', payment: 1, incoterm: 'DAP', ship: 8, bill: null, sp: sp2.id },
      // 组织行已停用 → 仍取账户级；无地址；销售员已停用 → 不带出
      { key: 'C', payment: 1, incoterm: 'EXW', ship: null, bill: null, sp: null },
      // 全空 → fail-open 留空
      { key: 'D', payment: null, incoterm: null, ship: null, bill: null, sp: null },
    ]

    const created = []
    try {
      for (const c of cases) {
        await withStep(page, testInfo, `客户 ${c.key} 新建订单默认带出`, async () => {
          const order = await createBo(page, 'sales_order', {
            order_no: `SCN-SO-W9-E2E-${c.key}-${stamp}`,
            order_type_id: ORDER_TYPE_STD,
            order_date: '2026-10-26',
            org_id: ORG_EAST,
            sales_org_id: ORG_EAST,
            currency_id: 8,
            customer_account_id: cust[c.key].id,
          })
          created.push(order.id)

          const fresh = await readBo(page, 'sales_order', order.id)
          expect(blankToNull(fresh.payment_term_id), `客户${c.key} 账期`)
            .toBe(c.payment)
          expect(blankToNull(fresh.incoterm_code), `客户${c.key} 贸易条款`)
            .toBe(c.incoterm)
          expect(blankToNull(fresh.ship_to_address_id), `客户${c.key} 收货地址`)
            .toBe(c.ship)
          expect(blankToNull(fresh.bill_to_address_id), `客户${c.key} 收票地址`)
            .toBe(c.bill)
          expect(blankToNull(fresh.salesperson_id), `客户${c.key} 销售员`)
            .toBe(c.sp)
        })
      }
    } finally {
      for (const id of created) {
        await dropBo(page, 'sales_order', id)
      }
    }
  })
})

test.describe('SO-SCN: 定价与行默认值', () => {
  test('FE-08 W2-A 服务行默认值只补空', async ({ page }, testInfo) => {
    const order = await findOrder(page, ORDER_SVC)
    const svcItem = await findByField(page, 'item', 'code', 'SCN-SO-ITEM-SVC-STD')
    const used = new Set((await fetchOrderLines(page, order.id))
      .map(l => String(l.line_no)))
    const nextLineNo = () => {
      let n = 90
      while (used.has(String(n))) n++
      used.add(String(n))
      return String(n)
    }

    const created = []
    try {
      await withStep(page, testInfo, '第一行全空 → 4 项默认值补齐', async () => {
        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: nextLineNo(),
          line_type_id: LINE_TYPE_SVC,
          item_id: svcItem.id,
          qty: 1,
          uom_id: UOM_FEA,
          unit_price: 200,
          tax_code_id: TAX_6,
        })
        created.push(line.id)
        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(fresh.billing_method, '计费方式取物料默认').toBe('fixed_price')
        expect(fresh.required_resource_type, '资源类型取物料默认')
          .toBe('technician')
        expect(Number(fresh.service_duration), '标准时长取物料默认').toBe(2)
        expect(fresh.duration_type, '时长单位取物料默认').toBe('day')
      })

      await withStep(page, testInfo, '第二行已填计费方式 → 不覆盖、其余照补', async () => {
        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: nextLineNo(),
          line_type_id: LINE_TYPE_SVC,
          item_id: svcItem.id,
          qty: 1,
          uom_id: UOM_FEA,
          unit_price: 200,
          tax_code_id: TAX_6,
          billing_method: 'milestone',
        })
        created.push(line.id)
        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(fresh.billing_method, '已填值不被默认值覆盖').toBe('milestone')
        expect(fresh.required_resource_type).toBe('technician')
        expect(Number(fresh.service_duration)).toBe(2)
        expect(fresh.duration_type).toBe('day')
      })
    } finally {
      for (const id of created) {
        await dropBo(page, 'sales_order_line', id)
      }
    }
  })

  test('FE-09 W1-A 取价失败码与手工价保护', async ({ page }, testInfo) => {
    const failCases = [
      { orderNo: ORDER_NOCAND, reason: 'NO_CANDIDATE' },
      { orderNo: ORDER_CCY, reason: 'CURRENCY_MISMATCH' },
    ]

    for (const c of failCases) {
      await withStep(page, testInfo, `${c.orderNo} 取价失败但订单保留`, async () => {
        const order = await findOrder(page, c.orderNo)
        const resp = await page.request.post(
          `/api/v1/sales-orders/${order.id}/reprice`)
        expect(resp.ok(), `POST reprice 应 200, 实际 ${resp.status()}`).toBe(true)
        const body = await resp.json()
        expect((body?.data ?? body)?.pricing_status, '抬头定价状态应为失败')
          .toBe('failed')

        const lines = await fetchOrderLines(page, order.id)
        expect(lines.length, '失败不阻保存，行仍保留').toBeGreaterThan(0)
        const trace = typeof lines[0].price_trace === 'string'
          ? JSON.parse(lines[0].price_trace)
          : lines[0].price_trace
        expect(trace?.reason, `${c.orderNo} 失败原因码`).toBe(c.reason)
        expect(blankToNull(lines[0].unit_price), '失败行不写单价').toBeNull()
      })
    }

    await withStep(page, testInfo, '手工价行改数量 → 单价不被覆盖', async () => {
      const order = await findOrder(page, ORDER_MANUAL)
      const lines = await fetchOrderLines(page, order.id)
      const line = lines.find(l => blankToNull(l.unit_price) !== null)
      expect(line, '应存在手工价行').toBeTruthy()
      expect(Number(line.unit_price), '种子手工价').toBe(999)
      expect(line.price_source, '来源为手工').toBe('manual')

      const upd = await page.request.put(
        `/api/v2/bo/sales_order_line/${line.id}`, { data: { qty: 3 } })
      expect(upd.ok(), `改数量应成功, 实际 ${upd.status()}`).toBe(true)
      try {
        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(Number(fresh.unit_price), '手工价不被重取').toBe(999)
        expect(fresh.price_source, '来源仍为手工').toBe('manual')
      } finally {
        await page.request.put(
          `/api/v2/bo/sales_order_line/${line.id}`, { data: { qty: 2 } })
      }
    })
  })

  test('FE-10 行单位默认取物料销售单位且不覆盖显式值', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const stamp = Date.now().toString().slice(-6)
    const su1 = await findByField(page, 'item', 'code', 'SCN-SO-MD-ITEM-SU1')  // KG + 销售单位 BOX(有换算)
    const su2 = await findByField(page, 'item', 'code', 'SCN-SO-MD-ITEM-SU2')  // KG + 无销售单位
    const cust = await findByField(page, 'customer_account', 'name', 'SCN-SO-客户A')

    let order = null
    const createdLines = []
    try {
      await withStep(page, testInfo, '建单并建行（不填单位）', async () => {
        order = await createBo(page, 'sales_order', {
          order_no: `SCN-SO-MD-E2E-UOM-${stamp}`,
          order_type_id: ORDER_TYPE_STD,
          order_date: '2026-10-26',
          org_id: ORG_EAST,
          sales_org_id: ORG_EAST,
          currency_id: 8,
          customer_account_id: cust.id,
        })

        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: '10',
          line_type_id: LINE_TYPE_STD,
          item_id: su1.id,
          qty: 2,
          unit_price: 10,
          tax_code_id: TAX_6,
        })
        createdLines.push(line.id)

        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(Number(fresh.uom_id), '未填单位 → 取物料销售单位 BOX(15)').toBe(15)
      })

      await withStep(page, testInfo, '显式填单位不被覆盖', async () => {
        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: '20',
          line_type_id: LINE_TYPE_STD,
          item_id: su1.id,
          qty: 1,
          uom_id: 12,
          unit_price: 10,
          tax_code_id: TAX_6,
        })
        createdLines.push(line.id)

        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(Number(fresh.uom_id), '显式单位 KG(12) 不被覆盖').toBe(12)
      })

      await withStep(page, testInfo, '物料无销售单位 → 回落基本单位', async () => {
        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: '30',
          line_type_id: LINE_TYPE_STD,
          item_id: su2.id,
          qty: 1,
          unit_price: 10,
          tax_code_id: TAX_6,
        })
        createdLines.push(line.id)

        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(Number(fresh.uom_id), '无销售单位 → 基本单位 KG(12)').toBe(12)
      })

      await withStep(page, testInfo, '详情页行单位展示', async () => {
        await navigateTo(page, `/detail/sales_order/${order.id}`)
        await waitForApiFn(page, `GET /api/v2/bo/sales_order/${order.id}`).catch(() => {})
        await openLineTab(page, testInfo, /BOX|箱/)
      })
    } finally {
      for (const id of createdLines) {
        await dropBo(page, 'sales_order_line', id)
      }
      if (order) {
        await dropBo(page, 'sales_order', order.id)
      }
    }
  })

  test('FE-11 W1-A 新建订单行自动取价', async ({ page }, testInfo) => {
    const cust = await findByField(page, 'customer_account', 'name', 'SCN-SO-客户A')
    const item = await findByField(page, 'item', 'code', 'SCN-SO-ITEM-CPU')
    const stamp = Date.now().toString().slice(-6)

    let order = null
    const createdLines = []
    try {
      await withStep(page, testInfo, '建单（客户 A / 2026-10-26 / 华东）', async () => {
        order = await createBo(page, 'sales_order', {
          order_no: `SCN-SO-W9-E2E-PRC-${stamp}`,
          order_type_id: ORDER_TYPE_STD,
          order_date: '2026-10-26',
          org_id: ORG_EAST,
          sales_org_id: ORG_EAST,
          currency_id: 8,
          customer_account_id: cust.id,
          price_date: '2026-10-26',
        })
      })

      await withStep(page, testInfo, '建行不填单价 → 自动取价 74.16', async () => {
        const line = await createBo(page, 'sales_order_line', {
          order_id: order.id,
          line_no: '10',
          line_type_id: LINE_TYPE_STD,
          item_id: item.id,
          qty: 5,
          uom_id: UOM_FEA,
          tax_code_id: TAX_13,
        })
        createdLines.push(line.id)

        const fresh = await readBo(page, 'sales_order_line', line.id)
        expect(Number(fresh.unit_price).toFixed(2), '客户价 80 → 9 折 → 3% 附加费')
          .toBe('74.16')
        expect(fresh.price_source, '来源应为价目表').toBe('rate_table')
      })

      await withStep(page, testInfo, '抬头定价状态回写 determined', async () => {
        const fresh = await readBo(page, 'sales_order', order.id)
        expect(fresh.pricing_status, '抬头定价状态应为已取价').toBe('determined')
      })
    } finally {
      for (const id of createdLines) {
        await dropBo(page, 'sales_order_line', id)
      }
      if (order) {
        await dropBo(page, 'sales_order', order.id)
      }
    }
  })

  test('FE-12 W1-A 取价轨迹回放', async ({ page }, testInfo) => {
    // 当前无独立 explain 端点，以行上持久化的 price_trace 回放命中轨迹
    const order = await findOrder(page, ORDER_PRICE)

    await withStep(page, testInfo, '重取价并回放行轨迹', async () => {
      const resp = await page.request.post(
        `/api/v1/sales-orders/${order.id}/reprice`)
      expect(resp.ok(), `POST reprice 应 200, 实际 ${resp.status()}`).toBe(true)

      const lines = await fetchOrderLines(page, order.id)
      const priced = lines.find(l => blankToNull(l.unit_price) !== null)
      expect(priced, '应存在已取价行').toBeTruthy()

      const trace = typeof priced.price_trace === 'string'
        ? JSON.parse(priced.price_trace)
        : priced.price_trace
      expect(trace, '应写入取价轨迹').toBeTruthy()
      expect(blankToNull(trace.reason), '成功轨迹无失败原因').toBeNull()
      expect(trace.hit_ids?.length, '轨迹应记录命中价目行').toBeGreaterThan(0)
    })
  })

  test('FE-13 W0 确认后改行数量被守卫拦截', async ({ page }, testInfo) => {
    const order = await findOrder(page, ORDER_CONF)
    const lines = await fetchOrderLines(page, order.id)
    expect(lines.length, '确认单应含订单行').toBeGreaterThan(0)

    await withStep(page, testInfo, 'PUT qty=99 → 400 行写父单非草稿', async () => {
      const resp = await page.request.put(
        `/api/v2/bo/sales_order_line/${lines[0].id}`, { data: { qty: 99 } })
      expect(resp.status(), '确认后改数量应 400').toBe(400)
      const body = await resp.json()
      expect(body.success).toBe(false)
      expect(body.errors?.[0]?.rule, '规则码').toBe('line_write_parent_not_draft')
    })
  })

  test('FE-14 W2-A 服务属性反例', async ({ page }, testInfo) => {
    const cust = await findByField(page, 'customer_account', 'name', 'SCN-SO-客户A')
    const goods = await findByField(page, 'item', 'code', 'SCN-SO-ITEM-CPU')
    const svcOff = await findByField(page, 'item', 'code', 'SCN-SO-ITEM-SVC-OFF')
    const stamp = Date.now().toString().slice(-6)

    let order = null
    try {
      order = await createBo(page, 'sales_order', {
        order_no: `SCN-SO-W9-E2E-SVC-${stamp}`,
        order_type_id: ORDER_TYPE_STD,
        order_date: '2026-10-26',
        org_id: ORG_EAST,
        sales_org_id: ORG_EAST,
        currency_id: 8,
        customer_account_id: cust.id,
      })

      await withStep(page, testInfo, 'goods 行填计费方式被拒', async () => {
        const resp = await page.request.post('/api/v2/bo/sales_order_line', {
          data: {
            order_id: order.id,
            line_no: '10',
            line_type_id: LINE_TYPE_STD,
            item_id: goods.id,
            qty: 1,
            uom_id: UOM_FEA,
            unit_price: 10,
            tax_code_id: TAX_13,
            billing_method: 'fixed_price',
          },
        })
        expect(resp.status(), 'goods 行带服务列应 400').toBe(400)
        const body = await resp.json()
        // 创建接口（POST /api/v2/bo/<type>）只回 success/data/message，不回 errors，故按守卫文案断言
        expect(body.success, '应返回失败').toBe(false)
        expect(body.message, '拒绝原因').toContain('只有服务物料行可以填写服务属性')
      })

      await withStep(page, testInfo, '停用服务物料被拒', async () => {
        const resp = await page.request.post('/api/v2/bo/sales_order_line', {
          data: {
            order_id: order.id,
            line_no: '20',
            line_type_id: LINE_TYPE_SVC,
            item_id: svcOff.id,
            qty: 1,
            uom_id: UOM_FEA,
            unit_price: 200,
            tax_code_id: TAX_6,
          },
        })
        expect(resp.status(), '停用服务物料应 400').toBe(400)
        const body = await resp.json()
        expect(body.success, '应返回失败').toBe(false)
        expect(body.message, '拒绝原因').toContain('未签发或已停用，不能下单')
      })
    } finally {
      if (order) {
        await dropBo(page, 'sales_order', order.id)
      }
    }
  })

  test('FE-15 W2-D 确认时地址文本快照', async ({ page }, testInfo) => {
    const cust = await findByField(page, 'customer_account', 'name', 'SCN-SO-客户A')
    const ship = await fetchJson(page, `/api/v2/bo/address/${ADDR_SHIP}`)
    const bill = await fetchJson(page, `/api/v2/bo/address/${ADDR_BILL}`)

    // 确认单不可删除，用固定单号幂等复用
    let order = await findOrderOrNull(page, ORDER_ADDR)
    if (!order) {
      order = await createBo(page, 'sales_order', {
        order_no: ORDER_ADDR,
        order_type_id: ORDER_TYPE_STD,
        order_date: '2026-10-26',
        org_id: ORG_EAST,
        sales_org_id: ORG_EAST,
        currency_id: 8,
        customer_account_id: cust.id,
        ship_to_address_id: ADDR_SHIP,
        bill_to_address_id: ADDR_BILL,
      })
    }

    await withStep(page, testInfo, '推进到已确认', async () => {
      let fresh = await readBo(page, 'sales_order', order.id)
      if (fresh.status === 'draft') {
        const resp = await page.request.put(
          `/api/v2/bo/sales_order/${order.id}`, { data: { status: 'submitted' } })
        expect(resp.ok(), `提交应成功, 实际 ${resp.status()}`).toBe(true)
        fresh = await readBo(page, 'sales_order', order.id)
      }
      if (fresh.status === 'submitted') {
        const resp = await page.request.put(
          `/api/v2/bo/sales_order/${order.id}`, { data: { status: 'confirmed' } })
        expect(resp.ok(), `确认应成功, 实际 ${resp.status()}`).toBe(true)
      }
      fresh = await readBo(page, 'sales_order', order.id)
      expect(fresh.status, '订单应为已确认').toBe('confirmed')
    })

    await withStep(page, testInfo, '两列快照等于地址库全文', async () => {
      const fresh = await readBo(page, 'sales_order', order.id)
      expect(fresh.ship_to_address_text, '收货地址快照').toBe(ship.formatted_address)
      expect(fresh.bill_to_address_text, '收票地址快照').toBe(bill.formatted_address)
    })

    const originalStreet = ship.street
    try {
      await withStep(page, testInfo, '改地址库 street → 快照不变', async () => {
        const resp = await page.request.put(
          `/api/v2/bo/address/${ADDR_SHIP}`,
          { data: { street: `${originalStreet ?? ''}-E2E` } })
        expect(resp.ok(), `改地址库应成功, 实际 ${resp.status()}`).toBe(true)

        const addrAfter = await fetchJson(page, `/api/v2/bo/address/${ADDR_SHIP}`)
        expect(addrAfter.formatted_address, '地址库全文应变化')
          .not.toBe(ship.formatted_address)

        const fresh = await readBo(page, 'sales_order', order.id)
        expect(fresh.ship_to_address_text, '快照不随地址库变化')
          .toBe(ship.formatted_address)
      })
    } finally {
      const resp = await page.request.put(
        `/api/v2/bo/address/${ADDR_SHIP}`, { data: { street: originalStreet } })
      expect(resp.ok(), `还原地址库应成功, 实际 ${resp.status()}`).toBe(true)
    }

    await withStep(page, testInfo, '确认后改快照文本被拒', async () => {
      const resp = await page.request.put(
        `/api/v2/bo/sales_order/${order.id}`,
        { data: { ship_to_address_text: '试图覆盖快照' } })
      expect(resp.status(), '确认后改快照应 400').toBe(400)
      const body = await resp.json()
      expect(body.errors?.[0]?.rule, '规则码').toBe('address_snapshot_locked')
    })
  })
})
