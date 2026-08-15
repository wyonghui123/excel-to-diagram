/**
 * fetchAllPages.js - 分页全量拉取并行化 (纯异步函数, 便于单元测试)
 * ====================================================================
 * [目的] RelationScopeSection 首次加载关系/BO 时, 把串行逐页 (12 关系页 + 6 BO 页 ≈ 18 次 HTTP
 *   依次等待) 改为并行: 首页取 total → 剩余页 Promise.all 并发拉取 (限并发批次), 按页码拼接.
 *
 * [兼容] total 未知 (data 为数组) 时退化为"逐批拉到空页为止" (与旧串行语义一致, 仅提速).
 *
 * @param {Function} fetchPage - async (page) => { items, total }
 * @param {Object} opts - { pageSize, maxPages, concurrency }
 * @returns {Promise<Array>} 按页码顺序拼接的全部 items
 */
export async function fetchAllPagesParallel(fetchPage, { pageSize, maxPages, concurrency = 6 } = {}) {
  const first = await fetchPage(1)
  const pages = [first.items]
  if (first.items.length === 0) return []
  const total = (first.total != null && Number.isFinite(Number(first.total))) ? Number(first.total) : null
  const totalPages = total != null ? Math.min(maxPages, Math.ceil(total / pageSize)) : null
  if (totalPages != null && totalPages <= 1) return pages.flat()

  let nextPage = 2
  while (totalPages != null ? nextPage <= totalPages : nextPage <= maxPages) {
    const batch = []
    // 批次内页号同时受 maxPages 约束 (total 未知时 totalPages 为 null, 不能只靠 while 上限)
    for (let p = nextPage; p < nextPage + concurrency && p <= maxPages && (totalPages == null || p <= totalPages); p++) batch.push(p)
    if (batch.length === 0) break
    const results = await Promise.all(batch.map(fetchPage))
    let allEmpty = true
    batch.forEach((pg, idx) => {
      pages[pg - 1] = results[idx].items
      if (results[idx].items.length > 0) allEmpty = false
    })
    nextPage += batch.length
    if (totalPages == null && allEmpty) break  // total 未知: 全空页即结束
  }
  return pages.flat()
}
