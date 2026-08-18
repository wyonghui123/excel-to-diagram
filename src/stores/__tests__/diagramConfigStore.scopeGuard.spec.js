import { describe, it, expect } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDiagramConfigStore } from '../diagramConfigStore'

describe('diagramConfigStore scopeGuard', () => {
  it('默认阈值 = 软线 rels300/nodes250, 硬线 rels600/nodes400, ELK 为主', () => {
    setActivePinia(createPinia())
    const s = useDiagramConfigStore()
    expect(s.scopeGuard.enabled).toBe(true)
    expect(s.scopeGuard.elk.hardRels).toBe(600)
    expect(s.scopeGuard.elk.hardNodes).toBe(400)
    expect(s.scopeGuard.elk.softRels).toBe(300)
    expect(s.activeScopeGuard.softRels).toBe(300) // layoutEngine 默认 elk → active = elk
  })

  it('setScopeGuard 可整体/局部覆盖', () => {
    setActivePinia(createPinia())
    const s = useDiagramConfigStore()
    s.setScopeGuard({ enabled: false })
    expect(s.scopeGuard.enabled).toBe(false)
  })
})
