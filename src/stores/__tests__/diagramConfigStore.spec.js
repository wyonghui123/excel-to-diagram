/**
 * diagramConfigStore 单元测试
 * 目标覆盖率: 95%+
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDiagramConfigStore } from '../diagramConfigStore.js'

describe('diagramConfigStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('初始状态', () => {
    it('应该有正确的初始状态', () => {
      const store = useDiagramConfigStore()
      expect(store.chartType).toBe('')
      expect(store.previousChartType).toBe('')
      expect(store.chartTypeChanged).toBe(false)
      expect(store.colorScheme).toBe('default')
      expect(store.colorGroupBy).toBe('domain')
      expect(store.nodeTextColor).toBe('black')
      expect(store.centerScopeColor).toBe('#EDEDED')
      expect(store.centerDomainColor).toBe('#D9D9D9')
      expect(store.centerScopeHighlight).toBe(true)
      expect(store.centerDomain).toBe('')
      expect(store.centerScope).toEqual([])
      expect(store.layoutTemplate).toBe('default')
      expect(store.layoutEngine).toBe('elk')
      expect(store.layoutType).toBe('grouped')
      expect(store.assignmentMode).toBe('auto')
      expect(store.customColors).toEqual({})
      expect(store.positions).toEqual([])
      expect(store.preserveModelOrder).toBe(false)
      expect(store.hideLinkLabelTails).toBeNull()
      expect(store.annotationPanelPosition).toBe('bottom')
      expect(store.showAnnotationIcons).toBe(false)
      expect(store.useUnifiedRenderer).toBe(true)
      expect(store.mermaidMaxTextSize).toBe(500000)
    })
  })

  describe('配色相关 actions', () => {
    it('updateColorScheme 应该更新配色方案', () => {
      const store = useDiagramConfigStore()
      store.updateColorScheme('dark')
      expect(store.colorScheme).toBe('dark')
    })

    it('updateColorGroupBy 应该更新分组方式', () => {
      const store = useDiagramConfigStore()
      store.updateColorGroupBy('subDomain')
      expect(store.colorGroupBy).toBe('subDomain')
    })

    it('updateNodeTextColor 应该更新节点文字颜色', () => {
      const store = useDiagramConfigStore()
      store.updateNodeTextColor('white')
      expect(store.nodeTextColor).toBe('white')
    })

    it('updateCenterScopeColor 应该更新中心范围颜色', () => {
      const store = useDiagramConfigStore()
      store.updateCenterScopeColor('#FF0000')
      expect(store.centerScopeColor).toBe('#FF0000')
    })

    it('updateCenterDomainColor 应该更新中心领域颜色', () => {
      const store = useDiagramConfigStore()
      store.updateCenterDomainColor('#00FF00')
      expect(store.centerDomainColor).toBe('#00FF00')
    })

    it('updateCenterScopeHighlight 应该更新高亮状态', () => {
      const store = useDiagramConfigStore()
      store.updateCenterScopeHighlight(false)
      expect(store.centerScopeHighlight).toBe(false)
    })
  })

  describe('中心范围相关 actions', () => {
    it('updateCenterDomain 应该更新中心领域', () => {
      const store = useDiagramConfigStore()
      store.updateCenterDomain('供应链云')
      expect(store.centerDomain).toBe('供应链云')
    })

    it('updateCenterScope 应该更新中心范围', () => {
      const store = useDiagramConfigStore()
      store.updateCenterScope(['BO001', 'BO002'])
      expect(store.centerScope).toEqual(['BO001', 'BO002'])
    })

    it('updateCenterScope 应该处理非数组输入', () => {
      const store = useDiagramConfigStore()
      store.updateCenterScope('BO001')
      expect(store.centerScope).toEqual([])
    })

    it('updateCenterScopeMarkers 应该更新标记', () => {
      const store = useDiagramConfigStore()
      const markers = {
        domains: new Map([['1', true]]),
        subDomains: new Map(),
        serviceModules: new Map()
      }
      store.updateCenterScopeMarkers(markers)
      expect(store.centerScopeMarkers.domains.has('1')).toBe(true)
    })
  })

  describe('图表类型相关 actions', () => {
    it('updateChartType 应该更新图表类型', () => {
      const store = useDiagramConfigStore()
      store.updateChartType('businessObject')
      expect(store.chartType).toBe('businessObject')
    })

    it('updateChartType 应该记录之前类型', () => {
      const store = useDiagramConfigStore()
      store.updateChartType('serviceModule')
      store.updateChartType('businessObject')
      expect(store.previousChartType).toBe('serviceModule')
      expect(store.chartTypeChanged).toBe(true)
    })

    it('相同类型不应该触发 changed', () => {
      const store = useDiagramConfigStore()
      store.updateChartType('serviceModule')
      store.updateChartType('serviceModule')
      expect(store.chartTypeChanged).toBe(false)
    })

    it('updatePreviousChartType 应该更新之前类型', () => {
      const store = useDiagramConfigStore()
      store.updatePreviousChartType('oldType')
      expect(store.previousChartType).toBe('oldType')
    })

    it('setChartTypeChanged 应该设置 changed 状态', () => {
      const store = useDiagramConfigStore()
      store.setChartTypeChanged(true)
      expect(store.chartTypeChanged).toBe(true)
    })

    it('resetChartTypeChanged 应该重置 changed 状态', () => {
      const store = useDiagramConfigStore()
      store.setChartTypeChanged(true)
      store.resetChartTypeChanged()
      expect(store.chartTypeChanged).toBe(false)
    })
  })

  describe('布局相关 actions', () => {
    it('updateLayoutTemplate 应该更新布局模板', () => {
      const store = useDiagramConfigStore()
      store.updateLayoutTemplate('custom')
      expect(store.layoutTemplate).toBe('custom')
    })

    it('updateLayoutEngine 应该更新布局引擎', () => {
      const store = useDiagramConfigStore()
      store.updateLayoutEngine('dagre')
      expect(store.layoutEngine).toBe('dagre')
    })

    it('updateLayoutType 应该更新布局类型', () => {
      const store = useDiagramConfigStore()
      store.updateLayoutType('linear')
      expect(store.layoutType).toBe('linear')
    })
  })

  describe('自定义配置 actions', () => {
    it('updateCustomColors 应该更新自定义颜色', () => {
      const store = useDiagramConfigStore()
      store.updateCustomColors({ primary: '#ff0000' })
      expect(store.customColors.primary).toBe('#ff0000')
    })

    it('updatePositions 应该更新位置', () => {
      const store = useDiagramConfigStore()
      store.updatePositions([{ x: 10, y: 20 }])
      expect(store.positions).toHaveLength(1)
    })

    it('updateHideLinkLabelTails 应该更新隐藏标签尾部', () => {
      const store = useDiagramConfigStore()
      store.updateHideLinkLabelTails(true)
      expect(store.hideLinkLabelTails).toBe(true)
    })

    it('updateLayoutControlConfig 应该更新布局控制配置', () => {
      const store = useDiagramConfigStore()
      const config = { enabled: true, groups: [] }
      store.updateLayoutControlConfig(config)
      expect(store.layoutControlConfig.enabled).toBe(true)
    })

    it('updateMermaidMaxTextSize 应该更新最大文本大小', () => {
      const store = useDiagramConfigStore()
      store.updateMermaidMaxTextSize(100000)
      expect(store.mermaidMaxTextSize).toBe(100000)
    })

    it('updateMermaidMaxTextSize 应该处理字符串输入', () => {
      const store = useDiagramConfigStore()
      store.updateMermaidMaxTextSize('200000')
      expect(store.mermaidMaxTextSize).toBe(200000)
    })

    it('updateAnnotationPanelPosition 应该更新批注面板位置', () => {
      const store = useDiagramConfigStore()
      store.updateAnnotationPanelPosition('right')
      expect(store.annotationPanelPosition).toBe('right')
    })

    it('updateShowAnnotationIcons 应该更新显示批注图标', () => {
      const store = useDiagramConfigStore()
      store.updateShowAnnotationIcons(true)
      expect(store.showAnnotationIcons).toBe(true)
    })

    it('updateAssignmentMode 应该更新分配模式', () => {
      const store = useDiagramConfigStore()
      store.updateAssignmentMode('manual')
      expect(store.assignmentMode).toBe('manual')
    })
  })

  describe('渲染器相关 actions', () => {
    it('fallbackToLegacyRenderer 应该切换到旧渲染器', () => {
      const store = useDiagramConfigStore()
      store.fallbackToLegacyRenderer()
      expect(store.useUnifiedRenderer).toBe(false)
    })
  })

  describe('重置配置', () => {
    it('resetConfig 应该重置所有配置', () => {
      const store = useDiagramConfigStore()
      store.updateChartType('businessObject')
      store.updateColorScheme('dark')
      store.updateCenterDomain('测试')
      store.updateLayoutEngine('dagre')
      store.updateCustomColors({ primary: '#ff0000' })

      store.resetConfig()
      expect(store.chartType).toBe('')
      expect(store.colorScheme).toBe('default')
      expect(store.centerDomain).toBe('')
      expect(store.layoutEngine).toBe('elk')
      expect(store.customColors).toEqual({})
      expect(store.useUnifiedRenderer).toBe(false)
    })
  })

  describe('getters', () => {
    it('centerBoCodes 应该返回 Set', () => {
      const store = useDiagramConfigStore()
      store.updateCenterScope(['BO001', 'BO002'])
      expect(store.centerBoCodes instanceof Set).toBe(true)
      expect(store.centerBoCodes.has('BO001')).toBe(true)
      expect(store.centerBoCodes.has('BO002')).toBe(true)
    })

    it('resolvedColorConfig 应该返回解析后的颜色配置', () => {
      const store = useDiagramConfigStore()
      store.updateColorScheme('dark')
      store.updateCustomColors({ primary: '#ff0000' })

      const config = store.resolvedColorConfig
      expect(config.colorScheme).toBe('dark')
      expect(config.customColors.primary).toBe('#ff0000')
    })

    it('isBusinessObjectChart 应该正确判断', () => {
      const store = useDiagramConfigStore()
      expect(store.isBusinessObjectChart).toBe(false)
      store.updateChartType('businessObject')
      expect(store.isBusinessObjectChart).toBe(true)
    })

    it('isServiceModuleChart 应该正确判断', () => {
      const store = useDiagramConfigStore()
      expect(store.isServiceModuleChart).toBe(false)
      store.updateChartType('serviceModule')
      expect(store.isServiceModuleChart).toBe(true)
    })
  })
})
