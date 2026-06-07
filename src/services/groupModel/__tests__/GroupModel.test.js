/**
 * GroupModel 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { GroupModel } from '../GroupModel.js'

describe('GroupModel', () => {
  // 测试数据：模拟 营销云/供应链云/制造云 结构
  const mockArchitectureGroups = [
    {
      id: 'domain_1',
      title: '营销云',
      elementRef: { code: '营销云' },
      layout: { enabled: true, direction: 'TB' },
      children: [
        {
          id: 'subdomain_1',
          title: '营销中台',
          elementRef: { code: '营销中台' },
          layout: { enabled: true, direction: 'LR' },
          children: []
        }
      ]
    },
    {
      id: 'domain_2',
      title: '供应链云',
      elementRef: { code: '供应链云' },
      layout: { enabled: true, direction: 'TB' },
      children: [
        {
          id: 'subdomain_2',
          title: '供应链计划',
          elementRef: { code: '供应链计划' },
          layout: { enabled: true, direction: 'LR' },
          children: [
            {
              id: 'service_1',
              title: '需求计划',
              elementRef: { code: 'DP' },
              layout: { enabled: true, direction: 'TB' },
              children: []
            },
            {
              id: 'service_2',
              title: '计划范围管理',
              elementRef: { code: 'PLM' },
              layout: { enabled: true, direction: 'TB' },
              children: []
            }
          ]
        }
      ]
    },
    {
      id: 'domain_3',
      title: '制造云',
      elementRef: { code: '制造云' },
      layout: { enabled: true, direction: 'TB' },
      children: []
    }
  ]

  describe('基础功能', () => {
    it('应该正确构建索引', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      expect(model.groups.size).toBe(7) // 3 domains + 2 subdomains + 2 services
      expect(model.rootIds).toHaveLength(3)
      expect(model.getById('domain_2')?.title).toBe('供应链云')
    })

    it('应该正确获取子元素', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const children = model.getChildren('domain_2')
      expect(children).toHaveLength(1)
      expect(children[0].title).toBe('供应链计划')
    })

    it('应该正确获取根分组', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const roots = model.getRootGroups()
      expect(roots).toHaveLength(3)
      expect(roots.map(r => r.title)).toContain('供应链云')
    })
  })

  describe('enabled 状态检查', () => {
    it('默认应该为 enabled', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      expect(model.isEnabled('domain_2')).toBe(true)
      expect(model.isEnabled('subdomain_2')).toBe(true)
    })

    it('应该正确检测 disabled 状态', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      
      const model = new GroupModel(groups)
      
      expect(model.isEnabled('domain_2')).toBe(false)
      expect(model.isEnabled('subdomain_2')).toBe(true) // 子元素状态不变
    })
  })

  describe('禁用祖先路径', () => {
    it('没有禁用祖先时应该返回空数组', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const path = model.getDisabledAncestorPath('subdomain_2')
      expect(path).toEqual([])
    })

    it('应该正确获取禁用祖先路径', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      
      const model = new GroupModel(groups)
      
      const path = model.getDisabledAncestorPath('subdomain_2')
      expect(path).toEqual(['供应链云'])
    })

    it('应该正确获取多层禁用祖先路径', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      groups[1].children[0].layout.enabled = false // 禁用供应链计划
      
      const model = new GroupModel(groups)
      
      const path = model.getDisabledAncestorPath('service_1')
      expect(path).toEqual(['供应链云', '供应链计划'])
    })
  })

  describe('显示标题', () => {
    it('没有禁用祖先时应该只显示标题', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const title = model.getDisplayTitle('subdomain_2')
      expect(title).toBe('供应链计划')
    })

    it('有禁用祖先时应该显示父路径', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      
      const model = new GroupModel(groups)
      
      const title = model.getDisplayTitle('subdomain_2')
      expect(title).toBe('供应链计划（供应链云）')
    })
  })

  describe('扁平化分组', () => {
    it('应该正确返回启用的分组', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const flattened = model.getFlattenedGroups()
      expect(flattened.length).toBeGreaterThanOrEqual(3) // 至少 3 个根 domain
    })

    it('禁用 domain 时应该提升子元素', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false // 禁用供应链云
      
      const model = new GroupModel(groups)
      
      const flattened = model.getFlattenedGroups()
      
      const supplyChainPlan = flattened.find(g => g.title === '供应链计划')
      expect(supplyChainPlan).toBeDefined()
      expect(supplyChainPlan._disabledAncestorPath).toEqual(['供应链云'])
    })

    it('禁用 subdomain 时应该提升 service 元素', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].children[0].layout.enabled = false // 禁用供应链计划
      
      const model = new GroupModel(groups)
      
      const flattened = model.getFlattenedGroups()
      
      const service1 = flattened.find(g => g.title === '需求计划')
      const service2 = flattened.find(g => g.title === '计划范围管理')
      
      expect(service1).toBeDefined()
      expect(service2).toBeDefined()
      expect(service1?._disabledAncestorPath).toContain('供应链计划')
    })
  })

  describe('用户配置合并', () => {
    it('应该正确合并用户配置', () => {
      const model = GroupModel.fromUserConfig(mockArchitectureGroups, {
        groups: [
          {
            id: 'domain_2',
            layout: { enabled: false, direction: 'LR' }
          }
        ]
      })
      
      expect(model.isEnabled('domain_2')).toBe(false)
      expect(model.getById('domain_2')?.layout?.direction).toBe('LR')
    })

    it('合并后应该正确显示父路径', () => {
      const model = GroupModel.fromUserConfig(mockArchitectureGroups, {
        groups: [
          {
            id: 'domain_2',
            layout: { enabled: false }
          }
        ]
      })
      
      const title = model.getDisplayTitle('subdomain_2')
      expect(title).toBe('供应链计划（供应链云）')
    })
  })

  describe('Mermaid 配置生成', () => {
    it('应该生成正确的 Mermaid 配置', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const config = model.toMermaidConfig()
      expect(config.enabled).toBe(true)
      expect(config.groups).toHaveLength(3)
    })

    it('应该包含正确的显示标题', () => {
      const groups = JSON.parse(JSON.stringify(mockArchitectureGroups))
      groups[1].layout.enabled = false
      
      const model = new GroupModel(groups)
      const displayTitle = model.getDisplayTitle('subdomain_2')
      
      expect(displayTitle).toContain('供应链计划')
      expect(displayTitle).toContain('供应链云')
    })
  })

  describe('缓存机制', () => {
    it('应该缓存扁平化结果', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const first = model.getFlattenedGroups()
      const second = model.getFlattenedGroups()
      
      expect(first).toBe(second) // 同一个引用
    })

    it('更新状态后应该清除缓存', () => {
      const model = new GroupModel(mockArchitectureGroups)
      
      const first = model.getFlattenedGroups()
      model.updateEnabled('domain_2', false)
      const second = model.getFlattenedGroups()
      
      expect(first).not.toBe(second)
      expect(second.length).toBeGreaterThanOrEqual(3) // 包含被提升的元素
    })
  })
})
