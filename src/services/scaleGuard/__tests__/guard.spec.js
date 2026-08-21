import { describe, it, expect } from 'vitest'
import { classify, buildEntryMessages, buildExpandMessages } from '../guard'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }

describe('scaleGuard guard', () => {
  it('classify 边界: 关系为主, 节点为辅', () => {
    expect(classify({ nodes: 50, relations: 100 }, cfg)).toBe('ok')
    expect(classify({ nodes: 300, relations: 200 }, cfg)).toBe('soft') // 节点>250
    expect(classify({ nodes: 100, relations: 350 }, cfg)).toBe('soft') // 关系>300
    expect(classify({ nodes: 200, relations: 650 }, cfg)).toBe('hard') // 关系>600
    expect(classify({ nodes: 500, relations: 100 }, cfg)).toBe('hard') // 节点>400
  })

  it('文案包含关系数 (主指标优先表述)', () => {
    const m = buildEntryMessages({ nodes: 320, relations: 650 }, cfg)
    expect(m.hard).toContain('650')
    expect(m.hard).toContain('关系')
    const soft = buildExpandMessages({ nodes: 260, relations: 200 }, cfg)
    expect(soft.soft).toContain('关系')
  })
})
