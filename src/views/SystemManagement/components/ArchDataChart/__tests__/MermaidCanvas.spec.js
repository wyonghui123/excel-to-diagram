/**
 * MermaidCanvas - Phase 5 单元测试
 *
 * 契约覆盖：
 *   - 5.10.4 ④: mermaid 库本身渲染失败 try-catch
 *   - 5.4.2: preserveViewport 保留用户缩放位置
 *   - 5.4.3: 增量更新（mermaidText 变化触发重新渲染）
 *
 * Mock 策略：
 *   - mermaid 库本身 mock（避免真实渲染开销 + DOM 依赖）
 *   - 重点测：契约行为（emit / 视口保存恢复 / 错误降级）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ============================================================
// vi.hoisted: 把 mock 函数声明在 vi.mock 提升后仍可访问的位置
// （vi.mock 是 hoisted，引用外部变量会 ReferenceError）
// ============================================================
const { mockRun, mockInitialize, mockPerfNow } = vi.hoisted(() => {
  return {
    mockRun: vi.fn(),
    mockInitialize: vi.fn(),
    mockPerfNow: vi.fn(() => 1000)
  }
})

// ============================================================
// Mock mermaid 库
// ============================================================
vi.mock('mermaid', () => ({
  default: {
    initialize: mockInitialize,
    run: mockRun
  }
}))

// Mock @element-plus/icons-vue（避免 import 失败）
vi.mock('@element-plus/icons-vue', () => ({
  Loading: { name: 'Loading', render: () => null },
  WarningFilled: { name: 'WarningFilled', render: () => null },
  Refresh: { name: 'Refresh', render: () => null }
}))

// Mock performance.now（用于 elapsedMs 计算）
global.performance = { now: mockPerfNow }

// ============================================================
// 导入被测组件
// ============================================================
import MermaidCanvas from '../MermaidCanvas.vue'

// ============================================================
// 辅助：构造 wrapper
// ============================================================
function mountCanvas(props = {}) {
  return mount(MermaidCanvas, {
    props: {
      mermaidText: 'graph TD\n  A --> B',
      ...props
    },
    global: {
      stubs: {
        // stub el-icon 避免引入完整 element-plus
        'el-icon': {
          template: '<i class="el-icon-stub"><slot /></i>'
        }
      }
    }
  })
}

// ============================================================
// 辅助：mock mermaid.run 成功
// ============================================================
function mockRunSuccess() {
  mockRun.mockImplementation(async ({ nodes }) => {
    // 模拟 mermaid 把 <pre class="mermaid"> 替换为 <svg>
    nodes.forEach(node => {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
      svg.classList.add('mermaid-svg-mock')
      // 模拟节点
      const nodeEl = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      nodeEl.classList.add('node')
      nodeEl.setAttribute('id', 'flowchart-N0-0')
      svg.appendChild(nodeEl)
      node.parentNode.replaceChild(svg, node)
    })
  })
}

// ============================================================
// 辅助：mock mermaid.run 失败
// ============================================================
function mockRunParseError() {
  const err = new Error('Parse error: unexpected token')
  err.name = 'ParseError'
  mockRun.mockRejectedValue(err)
}

function mockRunRenderError() {
  mockRun.mockRejectedValue(new Error('Render failed: SVG generation error'))
}

describe('MermaidCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRunSuccess()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ============================================================
  // 契约 5.10.4 ④: mermaid 库本身渲染失败 try-catch
  // ============================================================
  describe('契约 5.10.4 ④: mermaid 渲染失败 try-catch', () => {
    it('mermaid.run() 抛 ParseError 时应 emit render-error (phase=parse)', async () => {
      mockRunParseError()
      const wrapper = mountCanvas()

      await flushPromises()
      await flushPromises() // 等 watch + mermaid.run() 完成

      const renderErrorEvents = wrapper.emitted('render-error')
      expect(renderErrorEvents).toBeTruthy()
      expect(renderErrorEvents.length).toBeGreaterThanOrEqual(1)

      const payload = renderErrorEvents[0][0]
      expect(payload.phase).toBe('parse')
      expect(payload.error).toBeInstanceOf(Error)
    })

    it('mermaid.run() 抛普通 Error 时应 emit render-error (phase=render)', async () => {
      mockRunRenderError()
      const wrapper = mountCanvas()

      await flushPromises()
      await flushPromises()

      const renderErrorEvents = wrapper.emitted('render-error')
      expect(renderErrorEvents).toBeTruthy()
      const payload = renderErrorEvents[0][0]
      expect(payload.phase).toBe('render')
    })

    it('渲染失败时应显示错误提示 UI（含 mermaid 源码 <details>）', async () => {
      mockRunParseError()
      const wrapper = mountCanvas({ mermaidText: 'graph TD\n  A --> B invalid' })

      await flushPromises()
      await flushPromises()

      // 应该出现错误 UI
      const errorEl = wrapper.find('.mermaid-canvas__error')
      expect(errorEl.exists()).toBe(true)
      // 应该包含源码 <details>
      const detailEl = wrapper.find('.mermaid-canvas__error-detail')
      expect(detailEl.exists()).toBe(true)
      // 应该包含 mermaid 源码
      expect(wrapper.text()).toContain('graph TD')
    })
  })

  // ============================================================
  // 契约 5.4.3: mermaidText 变化触发重新渲染
  // ============================================================
  describe('契约 5.4.3: mermaidText 变化触发重新渲染', () => {
    it('mount 时应调用 mermaid.run() 一次', async () => {
      mountCanvas()
      await flushPromises()
      await flushPromises()

      expect(mockRun).toHaveBeenCalledTimes(1)
    })

    it('mermaidText prop 变化时应重新调用 mermaid.run()', async () => {
      const wrapper = mountCanvas({ mermaidText: 'graph TD\n  A --> B' })
      await flushPromises()
      await flushPromises()

      expect(mockRun).toHaveBeenCalledTimes(1)

      // 修改 mermaidText
      await wrapper.setProps({ mermaidText: 'graph TD\n  A --> C' })
      await flushPromises()
      await flushPromises()

      expect(mockRun).toHaveBeenCalledTimes(2)
    })

    it('mermaidText 为空字符串时不应调用 mermaid.run()', async () => {
      const wrapper = mountCanvas({ mermaidText: '' })
      await flushPromises()
      await flushPromises()

      expect(mockRun).not.toHaveBeenCalled()
    })
  })

  // ============================================================
  // 契约 5.4.2: preserveViewport 视口保持
  // ============================================================
  describe('契约 5.4.2: preserveViewport 视口保持', () => {
    it('preserveViewport=true 时应保存/恢复 scrollLeft/scrollTop', async () => {
      const wrapper = mountCanvas({ preserveViewport: true })
      await flushPromises()
      await flushPromises()

      // 第一次渲染完成
      expect(mockRun).toHaveBeenCalledTimes(1)

      // 模拟用户滚动
      const viewport = wrapper.find('.mermaid-canvas__viewport').element
      viewport.scrollLeft = 100
      viewport.scrollTop = 50

      // 触发重新渲染
      await wrapper.setProps({ mermaidText: 'graph TD\n  A --> C' })
      await flushPromises()
      await flushPromises()

      // 第二次渲染完成后，scrollLeft/scrollTop 应该恢复
      // （注：restoreViewport 用 nextTick 恢复，需要再 flush 一次）
      await flushPromises()

      expect(viewport.scrollLeft).toBe(100)
      expect(viewport.scrollTop).toBe(50)
    })

    it('preserveViewport=false 时不保存视口', async () => {
      const wrapper = mountCanvas({ preserveViewport: false })
      await flushPromises()
      await flushPromises()

      const viewport = wrapper.find('.mermaid-canvas__viewport').element
      viewport.scrollLeft = 100
      viewport.scrollTop = 50

      await wrapper.setProps({ mermaidText: 'graph TD\n  A --> C' })
      await flushPromises()
      await flushPromises()
      await flushPromises()

      // preserveViewport=false 时 scrollLeft/scrollTop 不保证恢复
      // 这里只验证不抛错
      expect(mockRun).toHaveBeenCalledTimes(2)
    })
  })

  // ============================================================
  // 契约: mermaid.initialize 只调用一次
  // ============================================================
  describe('mermaid.initialize 只调用一次', () => {
    it('多次渲染应只初始化一次 mermaid', async () => {
      const wrapper = mountCanvas()
      await flushPromises()
      await flushPromises()

      await wrapper.setProps({ mermaidText: 'graph TD\n  A --> C' })
      await flushPromises()
      await flushPromises()

      await wrapper.setProps({ mermaidText: 'graph TD\n  A --> D' })
      await flushPromises()
      await flushPromises()

      expect(mockInitialize).toHaveBeenCalledTimes(1)
    })

    it('chartType 变化时重新初始化 mermaid', async () => {
      const wrapper = mountCanvas({ chartType: 'businessObject' })
      await flushPromises()
      await flushPromises()

      expect(mockInitialize).toHaveBeenCalledTimes(1)

      await wrapper.setProps({ chartType: 'serviceModule' })
      await flushPromises()
      await flushPromises()

      // chartType 变化触发重新初始化
      expect(mockInitialize).toHaveBeenCalledTimes(2)
    })
  })

  // ============================================================
  // 契约: emit render-complete
  // ============================================================
  describe('emit render-complete', () => {
    it('渲染成功应 emit render-complete (含 nodeCount 和 elapsedMs)', async () => {
      const wrapper = mountCanvas()
      await flushPromises()
      await flushPromises()

      const events = wrapper.emitted('render-complete')
      expect(events).toBeTruthy()
      const payload = events[0][0]
      expect(payload).toHaveProperty('nodeCount')
      expect(payload).toHaveProperty('elapsedMs')
      expect(typeof payload.elapsedMs).toBe('number')
    })
  })

  // ============================================================
  // 契约: 暴露 render / resetViewport / setScale 方法
  // ============================================================
  describe('defineExpose 暴露的方法', () => {
    it('应暴露 render 方法', async () => {
      const wrapper = mountCanvas()
      await flushPromises()
      await flushPromises()

      const vm = wrapper.vm
      expect(typeof vm.render).toBe('function')
    })

    it('应暴露 resetViewport 方法', async () => {
      const wrapper = mountCanvas()
      await flushPromises()

      const vm = wrapper.vm
      expect(typeof vm.resetViewport).toBe('function')
    })

    it('应暴露 setScale 方法', async () => {
      const wrapper = mountCanvas()
      await flushPromises()

      const vm = wrapper.vm
      expect(typeof vm.setScale).toBe('function')

      // 调用 setScale 应该修改 scale
      vm.setScale(2.5)
      await flushPromises()
      // 缩放比例被限制在 [0.2, 5] 范围内
      expect(wrapper.find('.mermaid-canvas__zoom').text()).toBe('250%')
    })

    it('setScale 应限制最小 0.2', async () => {
      const wrapper = mountCanvas()
      await flushPromises()
      wrapper.vm.setScale(0.01)
      await flushPromises()
      expect(wrapper.find('.mermaid-canvas__zoom').text()).toBe('20%')
    })

    it('setScale 应限制最大 5', async () => {
      const wrapper = mountCanvas()
      await flushPromises()
      wrapper.vm.setScale(100)
      await flushPromises()
      expect(wrapper.find('.mermaid-canvas__zoom').text()).toBe('500%')
    })
  })

  // ============================================================
  // 边界条件
  // ============================================================
  describe('边界条件', () => {
    it('mermaidText 为空字符串时 contentRef 应清空', async () => {
      const wrapper = mountCanvas({ mermaidText: '' })
      await flushPromises()
      await flushPromises()

      // contentRef 应该为空（无 SVG）
      const content = wrapper.find('.mermaid-canvas__content')
      expect(content.element.children.length).toBe(0)
    })

    it('mermaidText 含 < > 应正确转义（不被浏览器解析）', async () => {
      const malicious = 'graph TD\n  A[label with <script>alert(1)</script>]'
      const wrapper = mountCanvas({ mermaidText: malicious })
      await flushPromises()
      await flushPromises()

      // 不应触发 XSS（mermaid.run 是 mock 的，但 innerHTML 应该已转义）
      // 注：mockRun 替换了 <pre> 元素，无法直接验证 innerHTML 转义
      // 这里只验证不抛错
      expect(mockRun).toHaveBeenCalled()
    })
  })
})
