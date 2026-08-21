/**
 * useInteraction 单测 — 拖拽状态判定 (wasDrag) 核心回归
 * ==============================================================
 *
 * 通过导入真实 useInteraction + 派发真实 mousedown/mousemove/mouseup 事件,
 * 断言 window.__mermaidDrag.wasDrag 的行为 — 这是 2026-08-16 修复的核心逻辑:
 *   "拖拽不取消高亮, 只有纯粹点击才取消高亮".
 *
 * 关键回归: 慢速小幅拖动(每次 <8px、累计 >8px) 也必须置 wasDrag=true.
 *   (旧实现用 translateX 推算增量, 慢速拖动永远不满足阈值 → 拖完高亮被误清)
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useInteraction } from '../useInteraction.js'

// 真实模块的全局拖拽状态 (import 时已创建)
const getDrag = () => (typeof window !== 'undefined' ? window.__mermaidDrag : null)

function setup() {
  const container = document.createElement('div')
  container.className = 'mermaid-container'
  const target = document.createElement('div')
  container.appendChild(target)
  const content = document.createElement('div')
  content.className = 'mermaid-content'
  document.body.appendChild(container)
  document.body.appendChild(content)

  const { addZoomAndPan } = useInteraction()
  addZoomAndPan({ value: container }, { value: container }, { value: content })

  return { container, target, content }
}

/** 触发 mousedown (左键) on target, 返回 current mousemove/mouseup dispatcher */
function mouseDown(target, x, y) {
  target.dispatchEvent(new MouseEvent('mousedown', {
    bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y
  }))
}
function mouseMove(x, y) {
  document.dispatchEvent(new MouseEvent('mousemove', {
    bubbles: true, cancelable: true, clientX: x, clientY: y
  }))
}
function mouseUp() {
  document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }))
}

describe('useInteraction — 拖拽状态判定 (wasDrag)', () => {
  beforeEach(() => {
    const d = getDrag()
    if (d) {
      d.isDragging = false
      d.wasDrag = false
      d.clientX = 0
      d.clientY = 0
    }
    document.body.innerHTML = ''
  })

  it('快速拖拽(单次位移 20px) → wasDrag=true', () => {
    const { target } = setup()
    mouseDown(target, 100, 200)
    mouseMove(120, 200)   // |120-100| + |200-200| = 20 > 8
    expect(getDrag().wasDrag).toBe(true)
    mouseUp()
    // mouseup 不清除 wasDrag (留给 click handler 消费)
    expect(getDrag().wasDrag).toBe(true)
  })

  it('慢速小幅拖拽(每次 4px, 累计 16px) → wasDrag=true [关键回归]', () => {
    const { target } = setup()
    mouseDown(target, 100, 200)
    mouseMove(104, 204)   // 4+4 = 8, 未 >8
    expect(getDrag().wasDrag).toBe(false)
    mouseMove(108, 208)   // 从起点算 8+8 = 16 >8
    expect(getDrag().wasDrag).toBe(true)
  })

  it('纯点击(鼠标抖动 5px) → wasDrag=false', () => {
    const { target } = setup()
    mouseDown(target, 100, 200)
    mouseMove(103, 202)   // 3+2 = 5, 不 >8
    expect(getDrag().wasDrag).toBe(false)
    mouseMove(102, 203)   // 从起点算 2+3 = 5
    expect(getDrag().wasDrag).toBe(false)
    mouseUp()
    expect(getDrag().wasDrag).toBe(false)
  })

  it('mousedown 重置上一次拖拽的 wasDrag', () => {
    const { target } = setup()
    // 第 1 次拖拽
    mouseDown(target, 100, 200)
    mouseMove(200, 300)   // 200 >8
    expect(getDrag().wasDrag).toBe(true)
    mouseUp()
    // 第 2 次 mousedown 重置
    mouseDown(target, 400, 500)
    expect(getDrag().wasDrag).toBe(false)
  })

  it('非左键 mousedown (button=1) 不进入拖动 → wasDrag 保持 false', () => {
    const { container, target } = setup()
    target.dispatchEvent(new MouseEvent('mousedown', {
      bubbles: true, cancelable: true, button: 1, clientX: 100, clientY: 200
    }))
    mouseMove(200, 300)
    expect(getDrag().isDragging).toBe(false)
    expect(getDrag().wasDrag).toBe(false)
  })

  it('toolbar 内 mousedown 不进入拖动', () => {
    const { container } = setup()
    const toolbar = document.createElement('button')
    toolbar.className = 'toolbar-btn'
    container.appendChild(toolbar)
    toolbar.dispatchEvent(new MouseEvent('mousedown', {
      bubbles: true, cancelable: true, button: 0, clientX: 10, clientY: 10
    }))
    mouseMove(50, 50)
    expect(getDrag().isDragging).toBe(false)
    expect(getDrag().wasDrag).toBe(false)
  })

  it('click handler 的 wasDrag 消费逻辑 (closeContextMenu 等价断言)', () => {
    const { target } = setup()
    // 纯点击 → wasDrag=false → click 可清除高亮
    mouseDown(target, 100, 200)
    mouseUp()
    expect(!!(window.__mermaidDrag && window.__mermaidDrag.wasDrag)).toBe(false)

    // 拖拽 → wasDrag=true → click 不清除高亮
    mouseDown(target, 100, 200)
    mouseMove(200, 300)
    mouseUp()
    expect(!!(window.__mermaidDrag && window.__mermaidDrag.wasDrag)).toBe(true)
  })
})