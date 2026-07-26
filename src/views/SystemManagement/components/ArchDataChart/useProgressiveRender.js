/**
 * useProgressiveRender - 渐进式渲染 composable
 *
 * 所属模块：嵌入式图表视图（Phase 5+ 性能优化）
 *
 * 应用场景：
 *   - 5000+ 节点大数据量时，mermaid 渲染后节点 click 事件绑定会阻塞主线程 200ms+
 *   - 用 requestIdleCallback / requestAnimationFrame 分批绑定，每批 200 个
 *   - 大数据量阈值警告：超过 5000 节点时 emit 'large-data-warning'
 *
 * 性能预算（spec §5.10.4 ④ 性能预算达成度）：
 *   - 5000 节点：渲染总耗时 < 1.5s（mermaid.run ~1s + 渐进式绑定 ~0.5s）
 *   - 10000 节点：渲染总耗时 < 3s
 *   - 主线程不被阻塞超过 50ms（每批绑定后让出）
 *
 * 核心契约：
 *   - bindNodesProgressive(svgEl, chartType): 分批绑定 .node click 事件
 *     返回 { cancel, promise }，cancel 可中断
 *   - countNodes(svgEl): 统计节点数
 *   - LARGE_DATA_THRESHOLD: 大数据量阈值（默认 5000）
 *   - BATCH_SIZE: 每批绑定节点数（默认 200）
 *
 * 边界条件：
 *   1. svgEl 为 null → 立即 resolve，不绑定
 *   2. 节点数为 0 → 立即 resolve
 *   3. 节点数 < BATCH_SIZE → 一次性绑定
 *   4. 浏览器不支持 requestIdleCallback → 降级到 setTimeout(0)
 *
 * 注：本 composable 不直接操作 mermaid.run()，只处理 mermaid 渲染后的渐进式事件绑定
 */
import { ref } from 'vue'

// 大数据量阈值：超过此值触发 'large-data-warning'
export const LARGE_DATA_THRESHOLD = 5000

// 每批绑定节点数
export const BATCH_SIZE = 200

// 每批之间的让出延迟（ms）：50ms ≈ 一帧 16.7ms × 3，用户感知不到卡顿
export const YIELD_DELAY_MS = 0

/**
 * 检测浏览器是否支持 requestIdleCallback
 */
const supportsRequestIdleCallback = typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function'

/**
 * 让出主线程：优先用 requestIdleCallback，降级到 requestAnimationFrame，再降级到 setTimeout
 *
 * @param {Function} callback - 让出后执行的回调
 * @returns {Function} cancel 函数
 */
function yieldToMainThread(callback) {
  let cancelFn

  if (supportsRequestIdleCallback) {
    const handle = window.requestIdleCallback(callback, { timeout: 100 })
    cancelFn = () => window.cancelIdleCallback(handle)
  } else if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    const handle = window.requestAnimationFrame(() => callback())
    cancelFn = () => window.cancelAnimationFrame(handle)
  } else {
    const handle = setTimeout(callback, YIELD_DELAY_MS)
    cancelFn = () => clearTimeout(handle)
  }

  return cancelFn
}

/**
 * 统计 SVG 中的节点数
 *
 * @param {Element} svgEl - SVG 根元素
 * @returns {number} 节点数（.node 元素数量）
 */
export function countNodes(svgEl) {
  if (!svgEl) return 0
  // SVG 中节点通常是 <g class="node">，也兼容 div
  return svgEl.querySelectorAll('.node').length
}

/**
 * 统计 SVG 中的边数
 *
 * @param {Element} svgEl - SVG 根元素
 * @returns {number} 边数（.edge, .edgePath, .relationship 元素数量）
 */
export function countEdges(svgEl) {
  if (!svgEl) return 0
  // mermaid 通常用 .edgePath 表示边
  return svgEl.querySelectorAll('.edgePath, .edge, .relationship').length
}

/**
 * 渐进式绑定节点 click 事件
 *
 * @param {Element} svgEl - SVG 根元素
 * @param {Function} onNodeClick - 节点点击回调 (node: Element) => void
 * @param {Object} options - 配置
 * @param {number} options.batchSize - 每批绑定节点数（默认 200）
 * @param {Function} options.onProgress - 进度回调 (bound, total) => void
 * @param {AbortSignal} options.signal - 中断信号（可选）
 * @returns {{ promise: Promise<void>, cancel: () => void }}
 */
export function bindNodesProgressive(svgEl, onNodeClick, options = {}) {
  const {
    batchSize = BATCH_SIZE,
    onProgress = null,
    signal = null
  } = options

  let cancelYield
  let cancelled = false
  let resolvePromise  // 保存 resolve 引用，cancel 时手动 resolve

  const promise = new Promise((resolve) => {
    resolvePromise = resolve

    // 边界 1: svgEl 为 null → 立即 resolve（不调用 onProgress）
    if (!svgEl) {
      resolve()
      return
    }

    const nodes = Array.from(svgEl.querySelectorAll('.node'))

    // 边界 2: 节点数为 0 → 立即 resolve
    if (nodes.length === 0) {
      if (onProgress) onProgress(0, 0)
      resolve()
      return
    }

    // 边界 3: 节点数 < batchSize → 一次性绑定
    if (nodes.length <= batchSize) {
      if (!cancelled && !signal?.aborted) {
        nodes.forEach(node => {
          node.style.cursor = 'pointer'
          node.addEventListener('click', onNodeClick, { once: false })
        })
        if (onProgress) onProgress(nodes.length, nodes.length)
      }
      resolve()
      return
    }

    // 渐进式：分批绑定
    let boundCount = 0

    function bindBatch() {
      // 检查中断信号（cancel() 或 AbortSignal.abort()）
      if (cancelled || signal?.aborted) {
        resolve()
        return
      }

      const end = Math.min(boundCount + batchSize, nodes.length)

      for (let i = boundCount; i < end; i++) {
        const node = nodes[i]
        node.style.cursor = 'pointer'
        node.addEventListener('click', onNodeClick, { once: false })
      }

      boundCount = end
      if (onProgress) onProgress(boundCount, nodes.length)

      // 还有剩余 → 让出主线程后继续
      if (boundCount < nodes.length && !cancelled && !signal?.aborted) {
        cancelYield = yieldToMainThread(bindBatch)
      } else {
        resolve()
      }
    }

    bindBatch()
  })

  return {
    promise,
    cancel: () => {
      // 关键：先标记 cancelled，防止 yieldToMainThread 回调再次触发 bindBatch
      cancelled = true
      // 再取消待执行的 yield
      if (cancelYield) cancelYield()
      // 关键：cancel 后必须手动 resolve promise，否则永远 pending
      // 注：bindBatch 内部如果已 resolve，再次 resolve 是 no-op
      if (resolvePromise) resolvePromise()
    }
  }
}

/**
 * 渐进式清理节点 click 事件
 *
 * 用于组件销毁前清理事件监听器，避免内存泄漏
 *
 * @param {Element} svgEl - SVG 根元素
 * @param {Function} onNodeClick - 节点点击回调（必须与 bindNodesProgressive 传入的相同引用）
 * @returns {Promise<void>}
 */
export function unbindNodes(svgEl, onNodeClick) {
  return new Promise((resolve) => {
    if (!svgEl) {
      resolve()
      return
    }

    const nodes = svgEl.querySelectorAll('.node')
    nodes.forEach(node => {
      node.removeEventListener('click', onNodeClick)
    })

    resolve()
  })
}

/**
 * useProgressiveRender - 渐进式渲染 composable
 *
 * @returns {{
 *   isLargeData: Ref<boolean>,
 *   bindingProgress: Ref<{ bound: number, total: number } | null>,
 *   bindNodes: (svgEl: Element, onNodeClick: Function, options?: Object) => Promise<void>,
 *   unbindAll: (svgEl: Element, onNodeClick: Function) => Promise<void>,
 *   checkLargeData: (svgEl: Element) => { nodeCount: number, edgeCount: number, isLarge: boolean }
 * }}
 */
export function useProgressiveRender() {
  const isLargeData = ref(false)
  const bindingProgress = ref(null)

  /**
   * 检查数据量是否过大
   * @param {Element} svgEl
   * @returns {{ nodeCount, edgeCount, isLarge }}
   */
  function checkLargeData(svgEl) {
    const nodeCount = countNodes(svgEl)
    const edgeCount = countEdges(svgEl)
    const isLarge = nodeCount >= LARGE_DATA_THRESHOLD

    isLargeData.value = isLarge

    return { nodeCount, edgeCount, isLarge }
  }

  /**
   * 渐进式绑定节点事件
   */
  async function bindNodes(svgEl, onNodeClick, options = {}) {
    bindingProgress.value = { bound: 0, total: 0 }

    const { promise, cancel } = bindNodesProgressive(svgEl, onNodeClick, {
      ...options,
      onProgress: (bound, total) => {
        bindingProgress.value = { bound, total }
        if (options.onProgress) options.onProgress(bound, total)
      },
      signal: options.signal
    })

    try {
      await promise
    } finally {
      bindingProgress.value = null
    }

    return { cancel }
  }

  /**
   * 清理所有节点事件
   */
  async function unbindAll(svgEl, onNodeClick) {
    await unbindNodes(svgEl, onNodeClick)
  }

  return {
    isLargeData,
    bindingProgress,
    bindNodes,
    unbindAll,
    checkLargeData
  }
}
