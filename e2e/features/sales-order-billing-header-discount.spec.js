/**
 * 销售订单 billing 计划行启用 + 抬头折扣分摊 - E2E
 *
 * 覆盖:
 *   A. billing 计划行守卫（7 类输入错误 + 合法创建 + 行内合计上限）
 *   B. 抬头折扣：范围守卫 / compute-apply 分离 / 分摊落库 / calc 留痕 / alloc 两级留痕 / 幂等 / 清零短路 / 非草稿冻结
 *
 * v2 铁律: import 自 auto-fixtures.js / 用 navigateTo / 不用 page.goto + waitForTimeout
 * 断言策略: view-config fields 为空 → 以 API 数据与错误码为主断言，UI 仅做轻量断言
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

const ORDER_NO = 'SCN-SO-W0-1'
const RECALC_ACTION = '/api/v2/action/sales_order.recalc_header_discount'

async function fetchJson(page, path) {
  const resp = await page.request.get(path)
  expect(resp.ok(), `GET ${path} 应成功, 实际 ${resp.status()}`).toBe(true)
  const body = await resp.json()
  return body?.data ?? body
}

async function fetchRaw(page, path) {
  const resp = await page.request.get(path)
  const body = await resp.json().catch(() => ({}))
  return { status: resp.status(), body }
}

async function postJson(page, path, data) {
  const resp = await page.request.post(path, { data })
  const body = await resp.json().catch(() => ({}))
  return { status: resp.status(), body }
}

async function putJson(page, path, data) {
  const resp = await page.request.put(path, { data })
  const body = await resp.json().catch(() => ({}))
  return { status: resp.status(), body }
}

async function deleteJson(page, path) {
  const resp = await page.request.delete(path)
  return { status: resp.status() }
}

function close(a, b, eps = 0.005) {
  return Math.abs(Number(a) - Number(b)) <= eps
}

async function findOrder(page, orderNo) {
  const data = await fetchJson(page, '/api/v2/bo/sales_order?page_size=200')
  const order = (data?.items || []).find(o => o.order_no === orderNo)
  expect(order, `应存在场景订单 ${orderNo}（先跑种子脚本）`).toBeTruthy()
  return order
}

async function readOrder(page, id) {
  return fetchRaw(page, `/api/v2/bo/sales_order/${id}`)
}

async function readLines(page, orderId) {
  const data = await fetchJson(
    page, `/api/v2/bo/sales_order_line?order_id=${orderId}&page_size=200`)
  return data?.items || []
}

async function readSchedules(page, orderId) {
  const data = await fetchJson(
    page, `/api/v2/bo/sales_order_schedule?order_id=${orderId}&page_size=200`)
  return data?.items || []
}

async function applyHeaderDiscount(page, orderId) {
  const { status, body } = await postJson(page, RECALC_ACTION, { order_id: orderId })
  return { status, body }
}

/** 抬头折扣归零 + 重算（短路恢复业务快照） */
async function resetHeaderDiscount(page, orderId) {
  await putJson(page, `/api/v2/bo/sales_order/${orderId}`, { header_discount_percent: null })
  await applyHeaderDiscount(page, orderId)
}

test.describe('SO-BILLING: billing 计划行守卫', () => {
  test('E2E-BILL-01 守卫报错 + 合法创建 + 行内合计上限', async ({ page }, testInfo) => {
    const order = await findOrder(page, ORDER_NO)
    expect(order.status, '本用例依赖草稿态订单').toBe('draft')

    const lines = await readLines(page, order.id)
    const line = lines.find(l => String(l.line_no) === '10')
    expect(line, `订单 ${ORDER_NO} 应含行号 10`).toBeTruthy()

    const created = []
    const cleanup = async () => {
      for (const id of created) {
        await deleteJson(page, `/api/v2/bo/sales_order_schedule/${id}`).catch(() => {})
      }
      // 预清理：删除该行已有 billing 计划行，避免合计被历史数据污染
      const rest = await readSchedules(page, order.id).catch(() => [])
      for (const s of rest) {
        if (String(s.line_id) === String(line.id) && s.schedule_kind === 'billing') {
          await deleteJson(page, `/api/v2/bo/sales_order_schedule/${s.id}`).catch(() => {})
        }
      }
    }
    await cleanup()

    const basePayload = () => ({
      order_id: order.id,
      line_id: line.id,
      schedule_kind: 'billing',
      schedule_no: 901,
      promised_date: '2026-12-01',
      billing_percent: 30,
    })

    const cases = [
      {
        name: '缺 promised_date',
        patch: { promised_date: null },
        pattern: /收款日期/,
      },
      {
        name: 'billing 行填 promised_qty',
        patch: { promised_qty: 5 },
        pattern: /promised_qty/,
      },
      {
        name: 'billing 行填 plant_location_id',
        patch: { plant_location_id: 1 },
        pattern: /plant_location_id/,
      },
      {
        name: '缺 billing_percent',
        patch: { billing_percent: null },
        pattern: /收款比例/,
      },
      {
        name: 'billing_percent = 0',
        patch: { billing_percent: 0 },
        pattern: /收款比例须大于 0/,
      },
      {
        name: 'billing_percent = 150',
        patch: { billing_percent: 150 },
        pattern: /收款比例须大于 0/,
      },
      {
        name: 'schedule_kind = service（未启用）',
        patch: { schedule_kind: 'service' },
        pattern: /尚未启用/,
      },
    ]

    try {
      for (const c of cases) {
        await withStep(page, testInfo, `守卫：${c.name} 应被拒`, async () => {
          const payload = { ...basePayload(), ...c.patch }
          const { status, body } = await postJson(page, '/api/v2/bo/sales_order_schedule', payload)
          expect(status, `${c.name} 应 400，实际 ${status}：${JSON.stringify(body)}`).toBe(400)
          expect(String(body?.message || ''), `${c.name} 的提示文案`).toMatch(c.pattern)
        })
      }

      let firstId = null
      await withStep(page, testInfo, '合法 billing 30% 应创建成功', async () => {
        const { status, body } = await postJson(page, '/api/v2/bo/sales_order_schedule', basePayload())
        expect(status, `合法计划行应 201，实际 ${status}：${JSON.stringify(body)}`).toBe(201)
        expect(body?.success).toBe(true)
        firstId = body?.data?.id
        expect(firstId, '创建应返回 id').toBeTruthy()
        created.push(firstId)
      })

      await withStep(page, testInfo, '回读派生列 billing_amount = 行净额 × 比例', async () => {
        const data = await fetchJson(page, `/api/v2/bo/sales_order_schedule/${firstId}`)
        expect(close(data.billing_percent, 30), `billing_percent 应为 30，实际 ${data.billing_percent}`).toBe(true)
        const expected = Math.round(Number(line.net_amount) * 30) / 100
        expect(
          close(data.billing_amount, expected),
          `billing_amount 应为 ${expected}，实际 ${data.billing_amount}`,
        ).toBe(true)
        expect(data.promised_qty, 'billing 行 promised_qty 应为空').toBeNull()
        expect(data.billing_amount > 0, 'billing_amount 应为正数').toBe(true)
      })

      await withStep(page, testInfo, '同行 billing 合计超 100 应被拒', async () => {
        const second = { ...basePayload(), schedule_no: 902, billing_percent: 80 }
        const { status, body } = await postJson(page, '/api/v2/bo/sales_order_schedule', second)
        expect(status, `合计 110 应 400，实际 ${status}`).toBe(400)
        expect(String(body?.message || '')).toMatch(/超过 100|合计/)
        if (body?.data?.id) created.push(body.data.id)
      })
    } finally {
      await cleanup()
    }
  })
})

test.describe('SO-HDISC: 抬头折扣分摊', () => {
  test('E2E-HD-01 守卫/分摊/留痕/幂等/清零短路', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    const order = await findOrder(page, ORDER_NO)
    expect(order.status, '本用例依赖草稿态订单').toBe('draft')

    const ORDER_ID = order.id
    const NETS = { 10: 300, 20: 25, 30: 13.34 }
    const EXPECT_DISCOUNT = 33.83

    await withStep(page, testInfo, '前置：清零抬头折扣恢复基线', async () => {
      await resetHeaderDiscount(page, ORDER_ID)
      const { body } = await readOrder(page, ORDER_ID)
      expect(close(body.data.net_amount, 338.34), `基线净额应为 338.34，实际 ${body.data.net_amount}`).toBe(true)
      expect(close(body.data.header_discount_amount, 0)).toBe(true)
      const lines = await readLines(page, ORDER_ID)
      for (const l of lines) {
        expect(close(l.header_discount_amount, 0), `行 ${l.line_no} 折扣应归零`).toBe(true)
        expect(close(l.net_amount, NETS[Number(l.line_no)]), `行 ${l.line_no} 净额应回到基线`).toBe(true)
      }
    })

    try {
      await withStep(page, testInfo, '范围守卫：percent=150 应被拒', async () => {
        const { status, body } = await putJson(
          page, `/api/v2/bo/sales_order/${ORDER_ID}`, { header_discount_percent: 150 })
        expect(status, `150% 应 400，实际 ${status}`).toBe(400)
        expect(body?.errors?.[0]?.rule, '应回规则码 HEADER_DISCOUNT_RANGE').toBe('HEADER_DISCOUNT_RANGE')
      })

      await withStep(page, testInfo, '保存 10% 只落比例，不落金额（compute/apply 分离）', async () => {
        const { status, body } = await putJson(
          page, `/api/v2/bo/sales_order/${ORDER_ID}`, { header_discount_percent: 10 })
        expect(status, `保存 10% 应 200，实际 ${status}：${JSON.stringify(body)}`).toBe(200)
        const { body: read } = await readOrder(page, ORDER_ID)
        expect(close(read.data.header_discount_percent, 10)).toBe(true)
        expect(
          close(read.data.header_discount_amount, 0),
          `未调 action 前不应写快照，实际 ${read.data.header_discount_amount}`,
        ).toBe(true)
        expect(close(read.data.net_amount, 338.34), '未调 action 前净额不变').toBe(true)
      })

      let applyData = null
      await withStep(page, testInfo, '调用 recalc action 触发 compute + apply', async () => {
        const { status, body } = await applyHeaderDiscount(page, ORDER_ID)
        expect(status, `action 应 200，实际 ${status}：${JSON.stringify(body)}`).toBe(200)
        expect(body?.success).toBe(true)
        expect(body?.message, '成功文案').toMatch(/抬头折扣重算成功/)
        applyData = body?.data || {}
        expect(close(applyData.discount_amount, EXPECT_DISCOUNT),
          `discount_amount 应为 ${EXPECT_DISCOUNT}，实际 ${applyData.discount_amount}`).toBe(true)
        expect(applyData.applied).toBe(1)
        expect(applyData.allocated_lines).toBe(3)
        expect(Array.isArray(applyData.header_result_ids) ? applyData.header_result_ids.length : 0,
          'compute 应落 4 步').toBe(4)
        expect(Array.isArray(applyData.line_result_ids) ? applyData.line_result_ids.length : 0,
          'apply 应落 3 行').toBe(3)
      })

      await withStep(page, testInfo, '抬头快照 = -D，净额下浮', async () => {
        const { body } = await readOrder(page, ORDER_ID)
        expect(close(body.data.header_discount_amount, -EXPECT_DISCOUNT),
          `抬头折扣金额应为 -${EXPECT_DISCOUNT}`).toBe(true)
        expect(close(body.data.net_amount, 304.51), `净额应为 304.51，实际 ${body.data.net_amount}`).toBe(true)
        expect(close(body.data.header_discount_percent, 10)).toBe(true)
      })

      await withStep(page, testInfo, '行级按净额比例分摊且行净额同步下浮', async () => {
        const lines = await readLines(page, ORDER_ID)
        const expectLine = {
          10: { hd: -30.0, net: 270.0 },
          20: { hd: -2.5, net: 22.5 },
          30: { hd: -1.33, net: 12.01 },
        }
        let hdSum = 0
        for (const l of lines) {
          const want = expectLine[Number(l.line_no)]
          expect(want, `行 ${l.line_no} 应参与分摊`).toBeTruthy()
          expect(close(l.header_discount_amount, want.hd),
            `行 ${l.line_no} 折扣应为 ${want.hd}，实际 ${l.header_discount_amount}`).toBe(true)
          expect(close(l.net_amount, want.net),
            `行 ${l.line_no} 净额应为 ${want.net}，实际 ${l.net_amount}`).toBe(true)
          hdSum += Number(l.header_discount_amount)
        }
        expect(close(hdSum, -EXPECT_DISCOUNT), `行折扣合计应等于 -${EXPECT_DISCOUNT}`).toBe(true)
      })

      await withStep(page, testInfo, 'calc_result 4 步留痕（CR_HD_{order}_10/15/18/20）', async () => {
        const rows = {}
        for (const id of applyData.header_result_ids) {
          const { status, body } = await fetchRaw(page, `/api/v2/bo/calc_result/${id}`)
          expect(status, `calc_result/${id} 应可读`).toBe(200)
          const d = body?.data || body
          rows[d.code] = d
        }
        const codes = Object.keys(rows).sort()
        expect(codes, '应落 4 步计算留痕').toEqual([
          `CR_HD_${ORDER_ID}_10`, `CR_HD_${ORDER_ID}_15`,
          `CR_HD_${ORDER_ID}_18`, `CR_HD_${ORDER_ID}_20`,
        ])
        const s10 = rows[`CR_HD_${ORDER_ID}_10`]
        const s15 = rows[`CR_HD_${ORDER_ID}_15`]
        const s18 = rows[`CR_HD_${ORDER_ID}_18`]
        const s20 = rows[`CR_HD_${ORDER_ID}_20`]
        expect(close(s10.base, 338.34), `第 10 步基价应为 338.34，实际 ${s10.base}`).toBe(true)
        expect(close(s15.amount, -EXPECT_DISCOUNT), `第 15 步折扣应为 -${EXPECT_DISCOUNT}，实际 ${s15.amount}`).toBe(true)
        expect(close(s15.rate, 10), `第 15 步比例应为 10，实际 ${s15.rate}`).toBe(true)
        expect(close(s18.base, 304.51), `第 18 步基额应为 304.51，实际 ${s18.base}`).toBe(true)
        expect(close(s20.base, 304.51), `第 20 步净额应为 304.51，实际 ${s20.base}`).toBe(true)
      })

      await withStep(page, testInfo, 'allocation_result 两级留痕（头级 1 + 行级 3）', async () => {
        const data = await fetchJson(page, '/api/v2/bo/allocation_result?page_size=500')
        const all = data?.items || []
        const mine = all.filter(a => String(a.document_id) === String(ORDER_ID)
          && a.document_type === 'sales_order')
        const header = mine.filter(a => a.level === 'header' && a.status === 'active')
        const lineRows = mine.filter(a => a.level === 'line' && a.status === 'active')
        expect(header.length, '应有 1 条头级分摊留痕').toBe(1)
        expect(close(header[0].amount, EXPECT_DISCOUNT), '头级分摊额应为 33.83').toBe(true)
        expect(header[0].sign, '头级分摊符号应为负').toBe('-')

        expect(lineRows.length, '应有 3 条行级分摊留痕').toBe(3)
        for (const r of lineRows) {
          expect(String(r.parent_id), '行级留痕应挂到头级').toBe(String(header[0].id))
          expect(r.sign).toBe('-')
          expect(r.status).toBe('active')
        }
        const byLine = {}
        for (const r of lineRows) byLine[String(r.document_line_id)] = Number(r.amount)
        const lines = await readLines(page, ORDER_ID)
        for (const l of lines) {
          const want = Math.abs(Number(l.header_discount_amount))
          expect(close(byLine[String(l.id)], want),
            `行 ${l.line_no} 留痕额应为 ${want}，实际 ${byLine[String(l.id)]}`).toBe(true)
        }
        const sum = lineRows.reduce((acc, r) => acc + Number(r.amount), 0)
        expect(close(sum, EXPECT_DISCOUNT), `行级留痕合计应为 ${EXPECT_DISCOUNT}`).toBe(true)
      })

      await withStep(page, testInfo, '幂等：重复调用业务快照不变且 calc id 稳定', async () => {
        const before = (await readOrder(page, ORDER_ID)).body.data
        const linesBefore = await readLines(page, ORDER_ID)
        const { status, body } = await applyHeaderDiscount(page, ORDER_ID)
        expect(status, '幂等重算应 200').toBe(200)
        expect(body?.success).toBe(true)
        expect(body?.data?.header_result_ids, 'calc 结果应就地更新，主键不漂移')
          .toEqual(applyData.header_result_ids)
        const after = (await readOrder(page, ORDER_ID)).body.data
        const linesAfter = await readLines(page, ORDER_ID)
        expect(close(after.net_amount, before.net_amount), '净额应幂等').toBe(true)
        expect(close(after.header_discount_amount, before.header_discount_amount), '折扣额应幂等').toBe(true)
        for (const l of linesBefore) {
          const a = linesAfter.find(x => String(x.id) === String(l.id))
          expect(close(a.net_amount, l.net_amount), `行 ${l.line_no} 净额应幂等`).toBe(true)
          expect(close(a.header_discount_amount, l.header_discount_amount), `行 ${l.line_no} 折扣应幂等`).toBe(true)
        }
      })

      await withStep(page, testInfo, 'UI 轻量断言：详情页展示折扣后净额', async () => {
        await navigateTo(page, `/detail/sales_order/${ORDER_ID}`)
        await waitForApiFn(page, `GET /api/v2/bo/sales_order/${ORDER_ID}`).catch(() => {})
        const text = (await page.locator('.object-page-content, .meta-object-page, body')
          .first().textContent()) || ''
        expect(text, '详情页应展示折扣后净额 304.51').toMatch(/304\.51/)
      })

      await withStep(page, testInfo, '非草稿订单折扣冻结（HEADER_DISCOUNT_LOCKED）', async () => {
        const data = await fetchJson(page, '/api/v2/bo/sales_order?page_size=200')
        const locked = (data?.items || []).find(o => o.status !== 'draft' && o.id !== ORDER_ID)
        if (!locked) {
          console.warn('[skip] 库中无非草稿订单，跳过冻结守卫断言')
          return
        }
        const { status, body } = await putJson(
          page, `/api/v2/bo/sales_order/${locked.id}`, { header_discount_percent: 10 })
        expect(status, `非草稿订单应 400，实际 ${status}`).toBe(400)
        expect(body?.errors?.[0]?.rule, '应回规则码 HEADER_DISCOUNT_LOCKED').toBe('HEADER_DISCOUNT_LOCKED')
      })

      await withStep(page, testInfo, 'percent 清零后 action 短路，快照归零', async () => {
        await resetHeaderDiscount(page, ORDER_ID)
        const { body } = await readOrder(page, ORDER_ID)
        expect(body.data.header_discount_percent, '比例应清空').toBeNull()
        expect(close(body.data.header_discount_amount, 0), '抬头折扣金额应归零').toBe(true)
        expect(close(body.data.net_amount, 338.34), `净额应回到 338.34，实际 ${body.data.net_amount}`).toBe(true)
        const lines = await readLines(page, ORDER_ID)
        for (const l of lines) {
          expect(close(l.header_discount_amount, 0), `行 ${l.line_no} 折扣应归零`).toBe(true)
          expect(close(l.net_amount, NETS[Number(l.line_no)]), `行 ${l.line_no} 净额应回到基线`).toBe(true)
        }
        const { status, body: again } = await applyHeaderDiscount(page, ORDER_ID)
        expect(status, '清零后重算应 200').toBe(200)
        expect(again?.data?.applied, '清零后 applied 应为 0').toBe(0)
        expect(again?.data?.allocated_lines, '清零后不应分摊').toBe(0)
      })
    } finally {
      await resetHeaderDiscount(page, ORDER_ID).catch(() => {})
    }
  })
})
