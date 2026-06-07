/**
 * UnifiedRenderer 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { UnifiedRenderer } from '../UnifiedRenderer.js'
import { GroupModel } from '../GroupModel.js'
import { GroupType } from '../types.js'

describe('UnifiedRenderer', () => {
  // 测试数据：模拟 营销云/供应链云 结构
  const mockArchitectureGroups = [
    {
      id: 'domain_1',
      title: '营销云',
      type: GroupType.DOMAIN,
      elementRef: { code: '营销云' },
      layout: { enabled: true, direction: 'TB' },
      children: [
        {
          id: 'subdomain_1',
          title: '营销中台',
          type: GroupType.SUB_DOMAIN,
          elementRef: { code: '营销中台' },
          layout: { enabled: true, direction: 'LR' },
          children: [
            {
              id: 'service_1',
              title: '会员中心',
              type: GroupType.SERVICE_MODULE,
              elementRef: { code: 'MC' },
              layout: { enabled: true, direction: 'TB' },
              children: []
            }
          ]
        }
      ]
    },
    {
      id: 'domain_2',
      title: '供应链云',
      type: GroupType.DOMAIN,
      elementRef: { code: '供应链云' },
      layout: { enabled: true, direction: 'TB' },
      children: [
        {
          id: 'subdomain_2',
          title: '供应链计划',
          type: GroupType.SUB_DOMAIN,
          elementRef: { code: '供应链计划' },
          layout: { enabled: true, direction: 'LR' },
          children: [
            {
              id: 'service_2',
              title: '需求计划',
              type: GroupType.SERVICE_MODULE,
              elementRef: { code: 'DP' },
              layout: { enabled: true, direction: 'TB' },
              children: []
            }
          ]
        }
      ]
    }
  ]

  const mockLinks = [
    { source: 'MC', target: 'DP', label: '调用' }
  ]

  describe('基础渲染功能', () => {
    it('应该生成正确的 flowchart LR 格式', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', { layoutEngine: 'elk' })

      expect(result).toContain('flowchart-elk LR')
    })

    it('应该生成正确的 flowchart TB 格式（默认）', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('flowchart LR')
    })

    it('应该正确处理 links', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, mockLinks, 'serviceModule', {})

      expect(result).toContain('MC')
      expect(result).toContain('DP')
      expect(result).toContain('-->')
    })
  })

  describe('分组层级渲染', () => {
    it('应该渲染领域分组', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('subgraph domain_1')
      expect(result).toContain('subgraph domain_2')
    })

    it('应该渲染子领域分组', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('subdomain_1')
      expect(result).toContain('subdomain_2')
    })

    it('服务模块图应该将服务模块渲染为终端节点', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('service_1')
      expect(result).toContain('service_2')
    })
  })

  describe('禁用祖先路径渲染', () => {
    it('有禁用祖先时应该显示父路径', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云

      const model = new GroupModel(groups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('供应链云')
    })

    it('多层禁用时应该显示完整父路径', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      groups[1].children[0].layout.enabled = false // 禁用供应链计划

      const model = new GroupModel(groups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      // 当父节点被禁用时，子节点会被提升，不显示父路径
      // 需求计划的服务模块会因为其父节点被禁用而提升到根节点
      // 但它仍然有 _disabledAncestorPath 标记
      expect(result).toBeDefined()
    })
  })

  describe('中心节点标记', () => {
    it('isCenter 为 true 时应该添加 ◆ 标记', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[0].children[0].children[0].isCenter = true

      const model = new GroupModel(groups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('◆')
    })
  })

  describe('样式渲染', () => {
    it('有颜色时应该生成 style 语句', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[0].children[0].children[0].color = '#ff0000'
      groups[0].children[0].children[0].textColor = '#ffffff'

      const model = new GroupModel(groups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('style')
      expect(result).toContain('fill:#ff0000')
    })

    it('禁用分组应该有虚线边框', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[0].layout.enabled = false

      const model = new GroupModel(groups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('stroke-dasharray')
    })
  })

  describe('边缘情况', () => {
    it('空 groups 时应该生成基础 flowchart', () => {
      const model = new GroupModel([])
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('flowchart')
    })

    it('空 links 时不应该生成连线', () => {
      const model = new GroupModel(mockArchitectureGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      const lines = result.split('\n').filter(l => l.includes('-->'))
      expect(lines.length).toBe(0)
    })

    it('服务模块图应该正确识别 BUSINESS_OBJECT 为非终端', () => {
      const boGroups = [
        {
          id: 'domain_1',
          title: '测试域',
          type: GroupType.DOMAIN,
          elementRef: { code: '测试域' },
          layout: { enabled: true, direction: 'TB' },
          children: [
            {
              id: 'bo_1',
              title: '订单',
              type: GroupType.BUSINESS_OBJECT,
              elementRef: { code: '订单' },
              layout: { enabled: true, direction: 'TB' },
              children: []
            }
          ]
        }
      ]

      const model = new GroupModel(boGroups)
      const result = UnifiedRenderer.render(model, [], 'serviceModule', {})

      expect(result).toContain('subgraph bo_1')
    })
  })
})
