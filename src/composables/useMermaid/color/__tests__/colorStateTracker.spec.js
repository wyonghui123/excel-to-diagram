/**
 * createColorStateTracker 单测 (2026-08-10)
 *
 * 覆盖核心场景: deep watch 下"原地修改对象引用不变, 颜色字段变化必须仍能被识别".
 * 这是解决"切换区分/不区分导致恒全量重建"bug 的关键保障.
 */
import { describe, it, expect } from 'vitest'
import { createColorStateTracker } from '../colorStateTracker'

describe('createColorStateTracker', () => {
  it('初始无变化: 刚创建时对相同数据 anyChanged=false', () => {
    const t = createColorStateTracker()
    // 模拟首次渲染前 snapshot
    t.snapshot({ colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} })
    expect(t.anyChanged({ colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} })).toBe(false)
  })

  it('原地修改 centerScopeHighlight (引用不变) 后仍识别变化', () => {
    const t = createColorStateTracker()
    const data = { colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} }
    t.snapshot(data)
    // 模拟 useDiagramData 原地修改: 同一对象, 仅改字段
    data.centerScopeHighlight = false
    expect(t.changed(data).centerScopeHighlight).toBe(true)
    expect(t.anyChanged(data)).toBe(true)
  })

  it('原地修改后 snapshot 刷新, 再判无变化', () => {
    const t = createColorStateTracker()
    const data = { colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} }
    t.snapshot(data)
    data.centerScopeHighlight = false
    t.snapshot(data)
    expect(t.anyChanged(data)).toBe(false)
  })

  it('识别 colorScheme / colorGroupBy / customColors 变化', () => {
    const t = createColorStateTracker()
    t.snapshot({ colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} })
    expect(t.changed({ colorGroupBy: 'domain', colorScheme: 'vibrant', centerScopeHighlight: true, customColors: {} }).colorScheme).toBe(true)
    expect(t.changed({ colorGroupBy: 'subDomain', colorScheme: 'default', centerScopeHighlight: true, customColors: {} }).colorGroupBy).toBe(true)
    expect(t.changed({ colorGroupBy: 'domain', colorScheme: 'default', centerScopeHighlight: true, customColors: { a: '#fff' } }).customColors).toBe(true)
  })

  it('state 快照独立, snapshot 不会污染传入对象', () => {
    const t = createColorStateTracker()
    const customColors = { a: '#fff' }
    t.snapshot({ colorGroupBy: 'domain', colorScheme: null, centerScopeHighlight: null, customColors })
    // 修改原 customColors 对象, tracker 内部快照不应受影响
    customColors.a = '#000'
    expect(t.changed({ colorGroupBy: 'domain', colorScheme: null, centerScopeHighlight: null, customColors: { a: '#fff' } }).customColors).toBe(false)
  })
})
