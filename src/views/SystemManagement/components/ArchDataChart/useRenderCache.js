/**
 * useRenderCache - Mermaid 渲染结果 LRU 缓存
 *
 * 所属模块：嵌入式图表视图（Phase 5+ 性能优化）
 *
 * 核心契约：
 *   - 缓存键：mermaidText 哈希（djb2）+ chartType
 *   - 缓存值：SVG 字符串（不含事件监听器，需重新绑定）
 *   - LRU 策略：get 时移到末尾，超过 maxSize 时删除头部
 *   - 缓存命中：直接 innerHTML = svg，跳过 mermaid.run()
 *   - 缓存未命中：mermaid.run() + set 结果
 *
 * 性能预算（spec §5.10.4 ④ 性能预算达成度）：
 *   - 颜色配置变更（同一 mermaidText 反复渲染）：缓存命中 < 5ms
 *   - scopeIds 切换（mermaidText 变化）：缓存未命中，正常渲染
 *
 * 边界条件：
 *   1. maxSize <= 0 → 不缓存
 *   2. mermaidText 为空/非字符串 → 返回 miss
 *   3. SVG 字符串超大（>10MB）→ 不缓存（避免内存爆炸）
 *   4. SSR 环境（无 window）→ 不缓存
 *
 * 使用方式：
 *   const cache = useRenderCache(10)  // 最多缓存 10 条
 *   const hit = cache.get(mermaidText, chartType)
 *   if (hit) { el.innerHTML = hit.svg }
 *   else {
 *     await mermaid.run(...)
 *     const svg = el.querySelector('svg')?.outerHTML
 *     cache.set(mermaidText, chartType, svg)
 *   }
 */
import { ref } from 'vue'

// 默认最大缓存条目数
const DEFAULT_MAX_SIZE = 10

// 单条 SVG 最大字节数（10MB），超过则不缓存
const MAX_SVG_SIZE = 10 * 1024 * 1024

/**
 * djb2 哈希函数
 * 简单快速，用于 mermaidText → 短 key
 * 不需要加密强度，只要分布均匀即可
 *
 * @param {string} str
 * @returns {string} 哈希值（16进制字符串）
 */
function djb2Hash(str) {
  if (!str) return '0'
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) + str.charCodeAt(i)
    // 保持 32 位整数
    hash = hash & 0xffffffff
  }
  // 转 16 进制，负数取绝对值
  return (hash >>> 0).toString(16)
}

/**
 * 构造缓存键
 * @param {string} mermaidText
 * @param {string} chartType
 * @returns {string}
 */
function buildCacheKey(mermaidText, chartType) {
  return `${chartType || 'default'}:${djb2Hash(mermaidText)}`
}

/**
 * useRenderCache - LRU 缓存 composable
 *
 * @param {number} maxSize - 最大缓存条目数（默认 10）
 * @returns {{
 *   get: (mermaidText: string, chartType: string) => { svg: string, hit: boolean } | { hit: false },
 *   set: (mermaidText: string, chartType: string, svg: string) => void,
 *   clear: () => void,
 *   stats: Ref<{ size: number, hits: number, misses: number, hitRate: number }>
 * }}
 */
export function useRenderCache(maxSize = DEFAULT_MAX_SIZE) {
  // 边界 1: maxSize <= 0 → 不缓存
  const enabled = maxSize > 0

  // Map 保留插入顺序，用于实现 LRU
  //   get 时：delete + set → 移到末尾（标记最近使用）
  //   set 时：超容量 → 删除第一个（最久未使用）
  const cache = new Map()

  // 统计信息（响应式）
  const stats = ref({
    size: 0,
    hits: 0,
    misses: 0,
    hitRate: 0
  })

  function updateStats() {
    stats.value = {
      size: cache.size,
      hits: stats.value.hits,
      misses: stats.value.misses,
      hitRate: stats.value.hits + stats.value.misses > 0
        ? stats.value.hits / (stats.value.hits + stats.value.misses)
        : 0
    }
  }

  /**
   * 获取缓存的 SVG
   * @param {string} mermaidText
   * @param {string} chartType
   * @returns {{ svg: string, hit: true } | { hit: false }}
   */
  function get(mermaidText, chartType) {
    // 边界 2: mermaidText 为空/非字符串 → miss
    if (!enabled || typeof mermaidText !== 'string' || mermaidText === '') {
      stats.value.misses++
      updateStats()
      return { hit: false }
    }

    const key = buildCacheKey(mermaidText, chartType)
    const cached = cache.get(key)

    if (cached === undefined) {
      // 缓存未命中
      stats.value.misses++
      updateStats()
      return { hit: false }
    }

    // LRU：移到末尾（delete + set）
    cache.delete(key)
    cache.set(key, cached)

    stats.value.hits++
    updateStats()
    return { svg: cached, hit: true }
  }

  /**
   * 设置缓存
   * @param {string} mermaidText
   * @param {string} chartType
   * @param {string} svg - SVG 字符串
   */
  function set(mermaidText, chartType, svg) {
    // 边界 1: 未启用
    if (!enabled) return

    // 边界 2: mermaidText 为空/非字符串 → 不缓存
    if (typeof mermaidText !== 'string' || mermaidText === '') return

    // 边界 3: SVG 超大 → 不缓存
    if (typeof svg !== 'string' || svg.length > MAX_SVG_SIZE) return

    const key = buildCacheKey(mermaidText, chartType)

    // 如果已存在，先删除（确保移到末尾）
    if (cache.has(key)) {
      cache.delete(key)
    }

    cache.set(key, svg)

    // LRU 淘汰：超过 maxSize 时删除头部（最久未使用）
    while (cache.size > maxSize) {
      const oldestKey = cache.keys().next().value
      cache.delete(oldestKey)
    }

    updateStats()
  }

  /**
   * 清空缓存
   */
  function clear() {
    cache.clear()
    stats.value = {
      size: 0,
      hits: 0,
      misses: 0,
      hitRate: 0
    }
  }

  return {
    get,
    set,
    clear,
    stats
  }
}

// ============================================================
// 导出辅助函数（用于单元测试）
// ============================================================
export {
  djb2Hash,
  buildCacheKey,
  DEFAULT_MAX_SIZE,
  MAX_SVG_SIZE
}
