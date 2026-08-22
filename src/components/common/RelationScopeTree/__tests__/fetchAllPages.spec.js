/**
 * fetchAllPages.spec.js - 分页全量拉取并行化
 * 回归保护: 2026-08-14 loadRelationships 首载 18 次串行 HTTP → 并行化
 */
import { describe, it, expect } from 'vitest'
import { fetchAllPagesParallel } from '../fetchAllPages.js'

// 生成 page: 每页 500, 数据为连续数字
function makeServer({ total = null, pageSize = 500, dataLen = 0 } = {}) {
  const calls = []
  const fetchPage = async (page) => {
    calls.push(page)
    const start = (page - 1) * pageSize
    // total 已知: 数据只有 total 条; total 未知: 前 dataLen 条后为空
    const remain = total != null ? Math.max(0, total - start) : Math.max(0, dataLen - start)
    const count = Math.min(pageSize, remain)
    const items = Array.from({ length: count }, (_, i) => start + i)
    return { items, total }
  }
  return { fetchPage, calls }
}

describe('fetchAllPagesParallel', () => {
  it('total 已知: 并行拉全部分页, 按页码顺序拼接', async () => {
    const { fetchPage, calls } = makeServer({ total: 1200, pageSize: 500 })
    const all = await fetchAllPagesParallel(fetchPage, { pageSize: 500, maxPages: 10, concurrency: 6 })
    expect(all.length).toBe(1200)
    expect(all[0]).toBe(0)
    expect(all[1199]).toBe(1199)
    expect(new Set(all).size).toBe(1200)          // 无重复
    expect(calls).toEqual([1, 2, 3])               // 首页 + 并行剩余页
  })

  it('单页 (total <= pageSize): 只拉首页', async () => {
    const { fetchPage, calls } = makeServer({ total: 300, pageSize: 500 })
    const all = await fetchAllPagesParallel(fetchPage, { pageSize: 500, maxPages: 10 })
    expect(all.length).toBe(300)
    expect(calls).toEqual([1])
  })

  it('total 未知: 逐批拉到空页为止 (数据正确, 可能多取几个空页但无缺失/重复)', async () => {
    const { fetchPage, calls } = makeServer({ total: null, pageSize: 500, dataLen: 1100 })
    const all = await fetchAllPagesParallel(fetchPage, { pageSize: 500, maxPages: 10, concurrency: 6 })
    expect(all.length).toBe(1100)
    expect(new Set(all).size).toBe(1100)          // 无重复
    expect(all[0]).toBe(0)
    expect(all[1099]).toBe(1099)
    expect(calls[calls.length - 1]).toBeLessThanOrEqual(10)  // 不超过 maxPages, 且已结束
  })

  it('首页为空: 返回空数组', async () => {
    const { fetchPage, calls } = makeServer({ total: 0, pageSize: 500 })
    const all = await fetchAllPagesParallel(fetchPage, { pageSize: 500, maxPages: 10 })
    expect(all).toEqual([])
    expect(calls).toEqual([1])
  })

  it('受 maxPages 上限保护', async () => {
    const { fetchPage, calls } = makeServer({ total: 100000, pageSize: 500 })
    const all = await fetchAllPagesParallel(fetchPage, { pageSize: 500, maxPages: 3 })
    expect(calls).toEqual([1, 2, 3])
    expect(all.length).toBe(1500)
  })
})
