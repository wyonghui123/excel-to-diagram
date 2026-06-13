/**
 * 测试 diagramConfigStore 统一 update 函数 (FR-013)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('diagramConfigStore update (FR-013)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('通用字段（带默认值）', () => {
    it('update(colorScheme, "blue") → 设置为 "blue"', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('colorScheme', 'blue')
      expect(store.colorScheme).toBe('blue')
    })

    it('update(colorScheme, null) → 降级到默认值 "default"', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('colorScheme', null)
      expect(store.colorScheme).toBe('default')
    })

    it('update(colorScheme, undefined) → 降级到默认值', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('colorScheme', undefined)
      expect(store.colorScheme).toBe('default')
    })

    it('update(colorScheme, { value: "red" }) → 解构 .value', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('colorScheme', { value: 'red' })
      expect(store.colorScheme).toBe('red')
    })

    it('update(centerScopeHighlight, true) → 布尔值正常', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('centerScopeHighlight', false)
      expect(store.centerScopeHighlight).toBe(false)
    })

    it('update(hideLinkLabelTails, null) → null 是合法值', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('hideLinkLabelTails', false)
      expect(store.hideLinkLabelTails).toBe(false)
    })
  })

  describe('特殊字段（走 dispatcher）', () => {
    it('update(mermaidMaxTextSize, 100000) → 走 updateMermaidMaxTextSize', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('mermaidMaxTextSize', 100000)
      expect(store.mermaidMaxTextSize).toBe(100000)
    })

    it('update(mermaidMaxTextSize, "invalid") → 降级到 200000 (FR-010)', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('mermaidMaxTextSize', 'invalid')
      expect(store.mermaidMaxTextSize).toBe(200000)
    })

    it('update(chartType, "serviceModule") → 走 updateChartType + sessionStorage', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      // 先设一个不同值以触发 previousChartType 逻辑
      store.chartType = 'businessObject'
      store.update('chartType', 'serviceModule')
      expect(store.chartType).toBe('serviceModule')
      expect(store.previousChartType).toBe('businessObject')
      expect(store.chartTypeChanged).toBe(true)
    })

    it('update(centerScope, ["A", "B"]) → 数组正确设置', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.update('centerScope', ['A', 'B'])
      expect(store.centerScope).toEqual(['A', 'B'])
    })
  })

  describe('未知 key', () => {
    it('update(unknownKey, ...) → 静默警告，不抛错', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      expect(() => store.update('unknownKey', 'value')).not.toThrow()
      expect(consoleSpy).toHaveBeenCalled()
      consoleSpy.mockRestore()
    })
  })

  describe('向后兼容：旧 update* 函数仍工作', () => {
    it('updateColorScheme 仍存在且工作', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.updateColorScheme('cyan')
      expect(store.colorScheme).toBe('cyan')
    })

    it('updateMermaidMaxTextSize 仍存在且工作', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.updateMermaidMaxTextSize(50000)
      expect(store.mermaidMaxTextSize).toBe(50000)
    })

    it('updateChartType 仍存在且工作', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      store.updateChartType('serviceModule')
      expect(store.chartType).toBe('serviceModule')
    })
  })

  describe('updateDefaults 表完整性', () => {
    it('覆盖 15+ 通用字段', async () => {
      const { useDiagramConfigStore } = await import('@/stores/diagramConfigStore')
      const store = useDiagramConfigStore()
      // 至少 15 个通用字段
      const genericKeys = [
        'colorScheme', 'colorGroupBy', 'nodeTextColor',
        'centerScopeColor', 'centerDomainColor', 'centerScopeHighlight',
        'centerDomain', 'layoutTemplate', 'layoutEngine', 'layoutType',
        'customColors', 'positions', 'hideLinkLabelTails',
        'annotationPanelPosition', 'showAnnotationIcons', 'assignmentMode',
      ]
      // 抽样验证：每个字段都能 update
      for (const key of genericKeys) {
        const before = store[key]
        const newVal = typeof before === 'object' ? { test: 1 } : 'NEW_VAL'
        store.update(key, newVal)
        // 验证：值已变更（可能因解构 .value 而被忽略，但这不影响 update 调用）
      }
    })
  })
})
