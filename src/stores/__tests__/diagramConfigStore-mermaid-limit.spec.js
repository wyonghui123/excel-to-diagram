/**
 * 测试 diagramConfigStore 的 mermaid 字符上限改造 (FR-010)
 *
 * 验证：
 * 1. 默认上限从 500000 降至 200000
 * 2. updateMermaidMaxTextSize 使用 200000 fallback
 * 3. resetConfig 恢复到 200000
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('diagramConfigStore mermaid limit (FR-010)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('default mermaidMaxTextSize is 200000 (reduced from 500000)', async () => {
    const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
    const store = useDiagramConfigStore()
    expect(store.mermaidMaxTextSize).toBe(200000)
  })

  it('updateMermaidMaxTextSize falls back to 200000 on invalid input', async () => {
    const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
    const store = useDiagramConfigStore()
    store.updateMermaidMaxTextSize('invalid')
    expect(store.mermaidMaxTextSize).toBe(200000)
  })

  it('updateMermaidMaxTextSize accepts valid number', async () => {
    const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
    const store = useDiagramConfigStore()
    store.updateMermaidMaxTextSize(100000)
    expect(store.mermaidMaxTextSize).toBe(100000)
  })

  it('resetConfig restores mermaidMaxTextSize to 200000', async () => {
    const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
    const store = useDiagramConfigStore()
    store.updateMermaidMaxTextSize(300000)
    expect(store.mermaidMaxTextSize).toBe(300000)
    store.resetConfig()
    expect(store.mermaidMaxTextSize).toBe(200000)
  })
})
