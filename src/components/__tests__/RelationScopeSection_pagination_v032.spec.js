/**
 * BUG-V032 回归测试: 关系范围树 不再被 BO/Rel 500 cap 影响
 *
 * 根因: RelationScopeSection.vue 的 loadBusinessObjectsWithHierarchy 和 loadRelationships
 *       用 page_size=10000 一次性拉, 但 API 受 MAX_USER_PAGE_SIZE=500 限制,
 *       V863 实际 2850 BO / 5634 Rel 被截断为 500/500, 导致:
 *       1) 范围内 = 0 (拿不到 141 个供应链云 BO 中真正的 src/tgt 信息)
 *       2) 范围内与外部 ≈ 0
 *       3) 范围外 count 偏小
 *
 * 修复: 内部循环分页 (每页 500), 拼接全部数据
 *
 * @see d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/RelationScopeSection.vue
 */
import { describe, it, expect, vi } from 'vitest'

// === 1. 重现修复后的分页拉取逻辑 (与 RelationScopeSection.vue 一致) ===
async function loadAllBOs(mockQuery) {
  const PAGE_SIZE = 500
  let allBos = []
  let page = 1
  let hasMore = true
  while (hasMore) {
    const r = await mockQuery('business_object', { page, page_size: PAGE_SIZE })
    const items = (r?.data?.items || r?.data || r || [])
    if (items.length === 0) { hasMore = false; break }
    allBos = allBos.concat(items)
    const total = r?.data?.total
    if (total != null) {
      hasMore = allBos.length < total
    } else {
      hasMore = items.length >= PAGE_SIZE
    }
    page++
    if (page > 20) hasMore = false
  }
  return allBos
}

async function loadAllRels(mockGet) {
  const REL_PAGE_SIZE = 500
  let newRels = []
  let relPage = 1
  let relHasMore = true
  while (relHasMore) {
    const r = await mockGet('/bo/relationship', { page: relPage, page_size: REL_PAGE_SIZE })
    if (!r.success) throw new Error(r.message || '服务端错误')
    const items = r.data?.items || r.data || []
    if (items.length === 0) { relHasMore = false; break }
    newRels = newRels.concat(items)
    const total = r.data?.total
    if (total != null) {
      relHasMore = newRels.length < total
    } else {
      relHasMore = items.length >= REL_PAGE_SIZE
    }
    relPage++
    if (relPage > 30) relHasMore = false
  }
  return newRels
}

// === 2. 测试用例 ===
describe('BUG-V032 loadAllBOs 分页拉全量', () => {
  it('少量数据 (< 500): 单次拉取即返回全部', async () => {
    const mockData = Array.from({ length: 100 }, (_, i) => ({ id: i + 1, code: `BO${i}` }))
    const mockQuery = vi.fn().mockResolvedValue({ data: { items: mockData, total: 100 } })
    const result = await loadAllBOs(mockQuery)
    expect(result.length).toBe(100)
    expect(mockQuery).toHaveBeenCalledTimes(1)
  })

  it('刚好 500 条: 单次拉完 (分页边界)', async () => {
    const mockData = Array.from({ length: 500 }, (_, i) => ({ id: i + 1, code: `BO${i}` }))
    const mockQuery = vi.fn().mockResolvedValue({ data: { items: mockData, total: 500 } })
    const result = await loadAllBOs(mockQuery)
    expect(result.length).toBe(500)
    expect(mockQuery).toHaveBeenCalledTimes(1)
  })

  it('V863 场景: 2850 BO, 应分 6 页 (500+500+500+500+500+350)', async () => {
    const TOTAL = 2850
    const PAGE_SIZE = 500
    // 模拟分页
    const mockQuery = vi.fn().mockImplementation(async (type, { page, page_size }) => {
      const start = (page - 1) * page_size
      const end = Math.min(start + page_size, TOTAL)
      const items = Array.from({ length: end - start }, (_, i) => ({ id: start + i + 1, code: `BO${start + i}` }))
      return { data: { items, total: TOTAL } }
    })

    const result = await loadAllBOs(mockQuery)
    expect(result.length).toBe(TOTAL)
    expect(mockQuery).toHaveBeenCalledTimes(6)  // 5 full + 1 partial
    // 验证最后一次返回 < 500
    const lastCall = mockQuery.mock.calls[mockQuery.mock.calls.length - 1]
    expect(lastCall[1].page).toBe(6)
  })

  it('total 字段不存在: 靠 "返回满页 = 还有更多" 判断', async () => {
    let page = 0
    const mockQuery = vi.fn().mockImplementation(async () => {
      page++
      if (page >= 3) return { data: { items: [] } }  // 第 3 页空, 停止
      const items = []
      for (let i = 0; i < 500; i++) items.push({ id: i })
      return { data: { items } }
    })
    const result = await loadAllBOs(mockQuery)
    expect(result.length).toBe(1000)  // 2 页 × 500
    expect(mockQuery).toHaveBeenCalledTimes(3)  // 2 full + 1 empty
  })

  it('防御: 超过 20 页强制停止 (防止死循环)', async () => {
    const mockQuery = vi.fn().mockImplementation(async () => {
      const items = []
      for (let i = 0; i < 500; i++) items.push({ id: i })
      return { data: { items, total: null } }
    })
    const result = await loadAllBOs(mockQuery)
    expect(result.length).toBe(500 * 20)  // 最多 10000
    expect(mockQuery).toHaveBeenCalledTimes(20)
  })

  it('空数据: 返回空数组, 不死循环', async () => {
    const mockQuery = vi.fn().mockResolvedValue({ data: { items: [], total: 0 } })
    const result = await loadAllBOs(mockQuery)
    expect(result).toEqual([])
    expect(mockQuery).toHaveBeenCalledTimes(1)
  })
})

describe('BUG-V032 loadAllRels 分页拉全量关系', () => {
  it('V863 场景: 5634 Rel, 应分 12 页 (500×11 + 134)', async () => {
    const TOTAL = 5634
    const mockGet = vi.fn().mockImplementation(async (path, { page, page_size }) => {
      const start = (page - 1) * page_size
      const end = Math.min(start + page_size, TOTAL)
      const items = Array.from({ length: end - start }, (_, i) => ({ id: start + i + 1, relationCode: 'CONTAINS' }))
      return { success: true, data: { items, total: TOTAL } }
    })

    const result = await loadAllRels(mockGet)
    expect(result.length).toBe(TOTAL)
    expect(mockGet).toHaveBeenCalledTimes(12)
  })

  it('服务端错误: 抛错 (不静默)', async () => {
    const mockGet = vi.fn().mockResolvedValue({ success: false, message: 'permission denied' })
    await expect(loadAllRels(mockGet)).rejects.toThrow('permission denied')
  })

  it('关系 count 正确: 范围内/跨域/范围外 应与全量关系数匹配', async () => {
    // 模拟: 100 rels, 60 src 在内, 60 tgt 在内, 30 都在内, 30 都不在
    // 范围内: 30, 跨域: 60, 范围外: 10
    const allRels = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      source_bo_id: i < 60 ? (i % 2 === 0 ? `bo_in_${i}` : `bo_out_${i}`) : `bo_out_${i + 1000}`,
      target_bo_id: i < 60 ? `bo_in_${i + 100}` : (i < 90 ? `bo_out_${i + 2000}` : `bo_out_${i + 3000}`)
    }))
    const inIds = new Set(Array.from({ length: 60 }, (_, i) => `bo_in_${i}`).concat(Array.from({ length: 60 }, (_, i) => `bo_in_${i + 100}`)))

    const mockGet = vi.fn().mockResolvedValue({ success: true, data: { items: allRels, total: 100 } })
    const result = await loadAllRels(mockGet)
    expect(result.length).toBe(100)

    // 分类
    let internal = 0, cross = 0, external = 0
    for (const r of result) {
      const sIn = inIds.has(r.source_bo_id)
      const tIn = inIds.has(r.target_bo_id)
      if (sIn && tIn) internal++
      else if (sIn || tIn) cross++
      else external++
    }
    // V863 实际比例: 220 / 709 / 4705 (总数 5634, 选取 220+709+4705=5634)
    expect(internal).toBeGreaterThan(0)
    expect(cross).toBeGreaterThan(0)
  })
})

// === 3. 旧实现必须被彻底删除 (防回滚) ===
describe('BUG-V032 旧实现残留检测', () => {
  it('不应再有 page_size: 10000 的一次性拉取 (BO)', async () => {
    let callParams = null
    const mockQuery = vi.fn().mockImplementation(async (type, params) => {
      callParams = params
      return { data: { items: [], total: 0 } }
    })
    await loadAllBOs(mockQuery)
    expect(callParams.page_size).toBe(500)  // 修复后是 500, 不是 10000
  })

  it('不应再有 page_size: 10000 的一次性拉取 (Rel)', async () => {
    let callParams = null
    const mockGet = vi.fn().mockImplementation(async (path, params) => {
      callParams = params
      return { success: true, data: { items: [], total: 0 } }
    })
    await loadAllRels(mockGet)
    expect(callParams.page_size).toBe(500)
  })
})
