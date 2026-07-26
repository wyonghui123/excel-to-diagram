/**
 * useProgressiveRender - Phase 5+ 单元测试
 *
 * 契约覆盖：
 *   - 渐进式绑定：每批 BATCH_SIZE 个节点，分批绑定
 *   - 让出主线程：每批之间用 requestIdleCallback / requestAnimationFrame / setTimeout
 *   - 大数据量阈值：超过 5000 节点触发 isLargeData=true
 *   - 中断信号：AbortSignal 触发后立即停止绑定
 *   - 边界条件：svgEl 为 null / 节点数 0 / 节点数 < BATCH_SIZE
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  useProgressiveRender,
  bindNodesProgressive,
  unbindNodes,
  countNodes,
  countEdges,
  LARGE_DATA_THRESHOLD,
  BATCH_SIZE
} from '../useProgressiveRender.js'

// ============================================================
// 辅助：创建 mock SVG 元素 + N 个 .node
// ============================================================
function createMockSvg(nodeCount = 0, edgeCount = 0) {
  const svg = document.createElement('div')
  svg.classList.add('mermaid-svg')

  for (let i = 0; i < nodeCount; i++) {
    const node = document.createElement('div')
    node.classList.add('node')
    node.setAttribute('data-id', `node-${i}`)
    svg.appendChild(node)
  }

  for (let i = 0; i < edgeCount; i++) {
    const edge = document.createElement('div')
    edge.classList.add('edgePath')
    svg.appendChild(edge)
  }

  return svg
}

describe('useProgressiveRender', () => {
  // ============================================================
  // 常量
  // ============================================================
  describe('常量', () => {
    it('LARGE_DATA_THRESHOLD 应为 5000', () => {
      expect(LARGE_DATA_THRESHOLD).toBe(5000)
    })

    it('BATCH_SIZE 应为 200', () => {
      expect(BATCH_SIZE).toBe(200)
    })
  })

  // ============================================================
  // countNodes / countEdges
  // ============================================================
  describe('countNodes / countEdges', () => {
    it('countNodes 应正确统计 .node 元素', () => {
      const svg = createMockSvg(5, 0)
      expect(countNodes(svg)).toBe(5)
    })

    it('countNodes 应统计嵌套的 .node', () => {
      const svg = document.createElement('div')
      const inner = document.createElement('div')
      inner.classList.add('node')
      svg.appendChild(inner)
      svg.appendChild(inner.cloneNode(true))
      expect(countNodes(svg)).toBe(2)
    })

    it('countNodes 边界：svgEl 为 null 应返回 0', () => {
      expect(countNodes(null)).toBe(0)
      expect(countNodes(undefined)).toBe(0)
    })

    it('countEdges 应正确统计 .edgePath 元素', () => {
      const svg = createMockSvg(0, 3)
      expect(countEdges(svg)).toBe(3)
    })

    it('countEdges 边界：svgEl 为 null 应返回 0', () => {
      expect(countEdges(null)).toBe(0)
    })
  })

  // ============================================================
  // bindNodesProgressive 基础行为
  // ============================================================
  describe('bindNodesProgressive 基础行为', () => {
    it('应给每个节点绑定 click 事件 + 设置 cursor:pointer', async () => {
      const svg = createMockSvg(5, 0)
      const onNodeClick = vi.fn()

      await bindNodesProgressive(svg, onNodeClick).promise

      const nodes = svg.querySelectorAll('.node')
      nodes.forEach(node => {
        expect(node.style.cursor).toBe('pointer')
      })

      // 触发某个节点的 click 事件
      const event = new MouseEvent('click', { bubbles: true })
      nodes[0].dispatchEvent(event)

      expect(onNodeClick).toHaveBeenCalled()
    })

    it('应触发 onProgress 回调', async () => {
      const svg = createMockSvg(5, 0)
      const onProgress = vi.fn()

      await bindNodesProgressive(svg, vi.fn(), { onProgress }).promise

      expect(onProgress).toHaveBeenCalled()
      // 最后一次调用应该是 bound = total = 5
      const lastCall = onProgress.mock.calls[onProgress.mock.calls.length - 1]
      expect(lastCall[0]).toBe(5)  // bound
      expect(lastCall[1]).toBe(5)  // total
    })
  })

  // ============================================================
  // 边界条件
  // ============================================================
  describe('边界条件', () => {
    it('svgEl 为 null 应立即 resolve，不调用 onProgress', async () => {
      const onProgress = vi.fn()
      const { promise } = bindNodesProgressive(null, vi.fn(), { onProgress })

      await promise

      expect(onProgress).not.toHaveBeenCalled()
    })

    it('节点数为 0 应立即 resolve', async () => {
      const svg = createMockSvg(0, 0)
      const onProgress = vi.fn()

      await bindNodesProgressive(svg, vi.fn(), { onProgress }).promise

      expect(onProgress).toHaveBeenCalledWith(0, 0)
    })

    it('节点数 < batchSize 应一次性绑定', async () => {
      const svg = createMockSvg(10, 0)
      const onProgress = vi.fn()

      await bindNodesProgressive(svg, vi.fn(), {
        batchSize: 200,
        onProgress
      }).promise

      // 只调用一次 onProgress
      expect(onProgress).toHaveBeenCalledTimes(1)
      expect(onProgress.mock.calls[0]).toEqual([10, 10])
    })

    it('节点数 = batchSize 应一次性绑定', async () => {
      const svg = createMockSvg(200, 0)

      await bindNodesProgressive(svg, vi.fn(), { batchSize: 200 }).promise

      const nodes = svg.querySelectorAll('.node')
      expect(nodes.length).toBe(200)
      nodes.forEach(node => {
        expect(node.style.cursor).toBe('pointer')
      })
    })

    it('节点数 > batchSize 应分批绑定', async () => {
      const svg = createMockSvg(250, 0)
      const onProgress = vi.fn()

      await bindNodesProgressive(svg, vi.fn(), {
        batchSize: 100,
        onProgress
      }).promise

      // 应该至少调用 3 次：100, 200, 250
      expect(onProgress.mock.calls.length).toBeGreaterThanOrEqual(3)
      // 最后一次 bound = total = 250
      const lastCall = onProgress.mock.calls[onProgress.mock.calls.length - 1]
      expect(lastCall).toEqual([250, 250])
    })
  })

  // ============================================================
  // 大数据量场景（5000+ 节点）
  // ============================================================
  describe('大数据量场景', () => {
    it('5000 节点应分批绑定（约 25 批）', async () => {
      const svg = createMockSvg(5000, 0)
      const onProgress = vi.fn()

      // 用更大的 batchSize 加速测试
      await bindNodesProgressive(svg, vi.fn(), {
        batchSize: 200,
        onProgress
      }).promise

      // 调用次数应为 ceil(5000/200) = 25
      expect(onProgress.mock.calls.length).toBe(25)

      // 所有节点应被绑定
      const nodes = svg.querySelectorAll('.node')
      nodes.forEach(node => {
        expect(node.style.cursor).toBe('pointer')
      })
    })

    it('10000 节点应正常完成绑定', async () => {
      const svg = createMockSvg(10000, 0)

      await bindNodesProgressive(svg, vi.fn(), { batchSize: 200 }).promise

      const nodes = svg.querySelectorAll('.node')
      expect(nodes.length).toBe(10000)
    })
  })

  // ============================================================
  // cancel 中断
  // ============================================================
  describe('cancel 中断', () => {
    it('cancel 调用后应停止绑定后续节点', async () => {
      const svg = createMockSvg(1000, 0)
      const onNodeClick = vi.fn()
      const onProgress = vi.fn()

      const { promise, cancel } = bindNodesProgressive(svg, onNodeClick, {
        batchSize: 100,
        onProgress
      })

      // 立即取消（可能在第一批之前或之中）
      cancel()

      await promise

      // 不期望所有节点都被绑定
      const boundNodes = Array.from(svg.querySelectorAll('.node')).filter(n => n.style.cursor === 'pointer')
      expect(boundNodes.length).toBeLessThan(1000)
    })

    it('AbortSignal 触发 abort 后应停止绑定', async () => {
      const svg = createMockSvg(1000, 0)
      const controller = new AbortController()
      const onProgress = vi.fn()

      const { promise } = bindNodesProgressive(svg, vi.fn(), {
        batchSize: 100,
        signal: controller.signal,
        onProgress
      })

      // 启动后立即 abort
      controller.abort()

      await promise

      // 不期望所有节点都被绑定
      const boundNodes = Array.from(svg.querySelectorAll('.node')).filter(n => n.style.cursor === 'pointer')
      expect(boundNodes.length).toBeLessThan(1000)
    })
  })

  // ============================================================
  // unbindNodes
  // ============================================================
  describe('unbindNodes', () => {
    it('应移除所有节点的 click 事件', async () => {
      const svg = createMockSvg(5, 0)
      const onNodeClick = vi.fn()

      await bindNodesProgressive(svg, onNodeClick).promise

      // 验证已绑定
      const nodes = svg.querySelectorAll('.node')
      nodes[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(onNodeClick).toHaveBeenCalledTimes(1)

      // 解绑
      await unbindNodes(svg, onNodeClick)

      // 再次触发 click 应不再调用
      onNodeClick.mockClear()
      nodes[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(onNodeClick).not.toHaveBeenCalled()
    })

    it('svgEl 为 null 应不抛错', async () => {
      await expect(unbindNodes(null, vi.fn())).resolves.toBeUndefined()
    })
  })

  // ============================================================
  // useProgressiveRender composable
  // ============================================================
  describe('useProgressiveRender composable', () => {
    it('初始状态：isLargeData=false, bindingProgress=null', () => {
      const { isLargeData, bindingProgress } = useProgressiveRender()
      expect(isLargeData.value).toBe(false)
      expect(bindingProgress.value).toBe(null)
    })

    it('checkLargeData 应返回节点数和 isLarge 标记', () => {
      const { checkLargeData } = useProgressiveRender()
      const svg = createMockSvg(100, 50)

      const result = checkLargeData(svg)
      expect(result.nodeCount).toBe(100)
      expect(result.edgeCount).toBe(50)
      expect(result.isLarge).toBe(false)
    })

    it('checkLargeData 节点数 >= 5000 应 isLarge=true', () => {
      const { checkLargeData, isLargeData } = useProgressiveRender()
      const svg = createMockSvg(5000, 0)

      const result = checkLargeData(svg)
      expect(result.isLarge).toBe(true)
      expect(isLargeData.value).toBe(true)
    })

    it('checkLargeData 边界：svgEl=null 应返回 0 不报错', () => {
      const { checkLargeData } = useProgressiveRender()
      const result = checkLargeData(null)
      expect(result.nodeCount).toBe(0)
      expect(result.edgeCount).toBe(0)
      expect(result.isLarge).toBe(false)
    })

    it('bindNodes 应更新 bindingProgress 并最终清空', async () => {
      const { bindNodes, bindingProgress } = useProgressiveRender()
      const svg = createMockSvg(250, 0)

      // bindNodes 是 async，过程中 bindingProgress 应该被更新
      await bindNodes(svg, vi.fn(), { batchSize: 100 })

      // 完成后应清空
      expect(bindingProgress.value).toBe(null)
    })

    it('unbindAll 应清理所有事件', async () => {
      const { bindNodes, unbindAll } = useProgressiveRender()
      const svg = createMockSvg(5, 0)
      const onNodeClick = vi.fn()

      await bindNodes(svg, onNodeClick)
      await unbindAll(svg, onNodeClick)

      const nodes = svg.querySelectorAll('.node')
      nodes[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(onNodeClick).not.toHaveBeenCalled()
    })
  })
})
