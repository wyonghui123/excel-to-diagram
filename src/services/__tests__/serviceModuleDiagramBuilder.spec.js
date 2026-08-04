/**
 * serviceModuleDiagramBuilder 单元测试
 */

import { describe, it, expect } from 'vitest'
import {
  buildServiceModuleDiagramData,
  LAYOUT_TEMPLATES
} from '../serviceModuleDiagramBuilder.js'

describe('serviceModuleDiagramBuilder', () => {
  // 测试数据
  const mockServiceModules = [
    { id: 'SM001', code: 'SM001', name: '会员中心', subDomain: '营销中台', domain: '营销云', isCenter: false },
    { id: 'SM002', code: 'SM002', name: '订单中心', subDomain: '营销中台', domain: '营销云', isCenter: true },
    { id: 'SM003', code: 'SM003', name: '需求计划', subDomain: '供应链计划', domain: '供应链云', isCenter: false },
    { id: 'SM004', code: 'SM004', name: '库存管理', subDomain: '供应链计划', domain: '供应链云', isCenter: false }
  ]

  const mockRelationships = [
    { sourceServiceModuleCode: 'SM001', targetServiceModuleCode: 'SM003', relationCode: '调用' },
    { sourceServiceModuleCode: 'SM002', targetServiceModuleCode: 'SM003', relationCode: '调用' },
    { sourceServiceModuleCode: 'SM003', targetServiceModuleCode: 'SM004', relationCode: '包含' }
  ]

  const mockDomainProducts = [
    {
      name: '营销云',
      modules: [
        { name: '营销中台' }
      ]
    },
    {
      name: '供应链云',
      modules: [
        { name: '供应链计划' }
      ]
    }
  ]

  describe('基础功能', () => {
    it('应该返回正确的图表数据结构', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts
      })

      expect(result).toHaveProperty('nodes')
      expect(result).toHaveProperty('links')
      expect(result).toHaveProperty('containers')
    })

    it('应该正确过滤服务模块', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutControlConfig: {
          enabled: true,
          groups: [
            {
              type: 'SERVICE_MODULE',
              elementCode: 'SM001'
            }
          ]
        }
      })

      expect(result.nodes.length).toBeLessThanOrEqual(mockServiceModules.length)
    })

    it('当 layoutControlConfig 未启用时应该返回所有服务模块', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutControlConfig: {
          enabled: false
        }
      })

      expect(result.nodes.length).toBe(mockServiceModules.length)
    })
  })

  describe('颜色配置', () => {
    it('应该使用指定的配色方案', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        colorScheme: 'vibrant'
      })

      expect(result.nodes.length).toBeGreaterThan(0)
      result.nodes.forEach(node => {
        expect(node).toHaveProperty('color')
      })
    })

    it('应该为不同子领域分配不同颜色', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        colorGroupBy: 'subDomain'
      })

      const subDomainColors = new Set()
      result.nodes.forEach(node => {
        if (node.subDomain) {
          subDomainColors.add(node.color)
        }
      })

      expect(subDomainColors.size).toBeGreaterThan(1)
    })

    it('中心服务模块应该有特殊颜色', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        centerScopeHighlight: true,
        centerServiceModuleCodes: ['SM002']
      })

      const centerNode = result.nodes.find(n => n.code === 'SM002')
      expect(centerNode).toBeDefined()
      expect(centerNode.color).toBeTruthy()
    })
  })

  describe('布局模板', () => {
    it('应该支持 DEFAULT 布局模板', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutTemplate: LAYOUT_TEMPLATES.DEFAULT
      })

      expect(result).toHaveProperty('nodes')
    })

    it('应该支持 GRID 布局模板', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutTemplate: LAYOUT_TEMPLATES.GRID
      })

      expect(result).toHaveProperty('nodes')
    })

    it('应该支持 HORIZONTAL 布局模板', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutTemplate: LAYOUT_TEMPLATES.HORIZONTAL
      })

      expect(result).toHaveProperty('nodes')
    })

    it('应该支持 VERTICAL 布局模板', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutTemplate: LAYOUT_TEMPLATES.VERTICAL
      })

      expect(result).toHaveProperty('nodes')
    })
  })

  describe('关系过滤', () => {
    it('当 layoutControlConfig 启用时应该过滤关系', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutControlConfig: {
          enabled: true,
          groups: [
            {
              type: 'SERVICE_MODULE',
              elementCode: 'SM001'
            }
          ]
        }
      })

      result.links.forEach(link => {
        expect(link.source).toBe('SM001')
      })
    })

    it('当关系两端的服务模块都被过滤时应该保留该关系', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        layoutControlConfig: {
          enabled: true,
          groups: [
            {
              type: 'SERVICE_MODULE',
              elementCode: 'SM003'
            },
            {
              type: 'SERVICE_MODULE',
              elementCode: 'SM004'
            }
          ]
        }
      })

      const hasSM3ToSM4 = result.links.some(
        l => (l.source === 'SM003' && l.target === 'SM004')
      )
      expect(hasSM3ToSM4).toBe(true)
    })
  })

  describe('边缘情况', () => {
    it('当 serviceModules 为空时应该返回空图表数据', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: [],
        serviceModuleRelationships: [],
        domainProducts: []
      })

      expect(result.nodes).toHaveLength(0)
      expect(result.links).toHaveLength(0)
    })

    it('当 serviceModuleRelationships 为空时应该返回空关系', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: [],
        domainProducts: mockDomainProducts
      })

      expect(result.links).toHaveLength(0)
    })

    it('当 centerSubDomain 未指定时应该使用第一个子领域', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        centerSubDomain: ''
      })

      expect(result.centerSubDomain).toBeTruthy()
    })

    it('当 centerServiceModuleCodes 为 null 时应该基于 isCenter 计算', () => {
      const result = buildServiceModuleDiagramData({
        serviceModules: mockServiceModules,
        serviceModuleRelationships: mockRelationships,
        domainProducts: mockDomainProducts,
        centerServiceModuleCodes: null
      })

      expect(result).toHaveProperty('nodes')
    })
  })

  describe('统一管道（preview 传入）', () => {
    // 递归收集容器树所有容器 id
    function collectContainerIds(containers, acc = new Set()) {
      for (const c of containers || []) {
        acc.add(c.id)
        collectContainerIds(c.children, acc)
      }
      return acc
    }

    it('preview 传入时走统一管道, 无重复容器（SM 只作为节点, 不作为容器）', () => {
      const preview = {
        domainProducts: [
          { name: '营销云', code: 'MKT', modules: [
            { name: '营销中台', code: 'MKT-M', submodules: [
              { name: '会员中心', code: 'SM001', businessObjects: [
                { id: 101, code: 'BO001', name: '会员' },
              ] },
            ] },
          ] },
        ],
        relationships: [],
      }
      const result = buildServiceModuleDiagramData({
        preview,
        chartType: 'serviceModule',
        colorGroupBy: 'subDomain',
        colorScheme: 'default',
      })
      const nodeIds = new Set(result.nodes.map(n => n.id))
      const containerIds = collectContainerIds(result.containers)
      // SM001 必须是显示节点（serviceModule 末端）
      expect(nodeIds.has('SM001')).toBe(true)
      // 容器树中不存在 id 与节点 id 相同的容器（SM 不作为 subgraph 边框重复出现）
      expect([...nodeIds].filter(id => containerIds.has(id))).toEqual([])
      // BO001 折叠进 SM, 不作为节点出现
      expect(nodeIds.has('BO001')).toBe(false)
      // 容器层级: 领域 → 子领域（nodeIds 含 SM001, 即 SM 归属于子领域容器, 正常层级）
      expect(result.containers).toHaveLength(1)
      expect(result.containers[0].layer).toBe('DOMAIN')
      expect(result.containers[0].children[0].layer).toBe('SUB_DOMAIN')
      expect(result.containers[0].children[0].nodeIds).toEqual(['SM001'])
    })
  })

  describe('LAYOUT_TEMPLATES 常量', () => {
    it('应该包含 DEFAULT 模板', () => {
      expect(LAYOUT_TEMPLATES.DEFAULT).toBe('default')
    })

    it('应该包含 GRID 模板', () => {
      expect(LAYOUT_TEMPLATES.GRID).toBe('grid')
    })

    it('应该包含 HORIZONTAL 模板', () => {
      expect(LAYOUT_TEMPLATES.HORIZONTAL).toBe('horizontal')
    })

    it('应该包含 VERTICAL 模板', () => {
      expect(LAYOUT_TEMPLATES.VERTICAL).toBe('vertical')
    })
  })
})
