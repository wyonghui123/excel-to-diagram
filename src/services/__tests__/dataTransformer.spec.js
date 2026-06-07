/**
 * dataTransformer 单元测试
 * 目标: 覆盖 src/services/dataTransformer.js 的 4 个 export 函数
 *
 * 实际 API:
 *   - buildServiceModules(serviceModuleMap: Map) -> Array
 *   - buildDomainProducts(moduleHierarchy: Map) -> Array
 *   - buildPreviewData({ businessObjects, serviceModules, relationships, serviceModuleRelationships, domainProducts }) -> Object
 *   - extractSubDomains(domainProducts: Array) -> Array<string>
 */

import { describe, it, expect } from 'vitest'
import {
  buildServiceModules,
  buildDomainProducts,
  buildPreviewData,
  extractSubDomains
} from '../dataTransformer.js'

describe('dataTransformer', () => {
  describe('buildServiceModules', () => {
    it('空 Map 应返回空数组', () => {
      const map = new Map()
      expect(buildServiceModules(map)).toEqual([])
    })

    it('单条目 Map 应输出 1 个 serviceModule', () => {
      const map = new Map([
        ['SM001', { name: '采购管理', code: 'SM001', subDomain: '采购', domain: '供应链云' }]
      ])
      const result = buildServiceModules(map)
      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        name: '采购管理',
        code: 'SM001',
        subDomain: '采购',
        domain: '供应链云',
        annotationCategory: 'info',
        annotationContent: ''
      })
    })

    it('多条目 Map 应保留所有条目 (顺序与 Map 迭代顺序一致)', () => {
      const map = new Map([
        ['SM001', { name: '采购', code: 'SM001', subDomain: '采购', domain: '供应链云' }],
        ['SM002', { name: '库存', code: 'SM002', subDomain: '库存', domain: '供应链云' }]
      ])
      const result = buildServiceModules(map)
      expect(result).toHaveLength(2)
      expect(result.map(r => r.code)).toEqual(['SM001', 'SM002'])
    })

    it('未提供 annotationCategory 时默认为 "info"', () => {
      const map = new Map([
        ['SM001', { name: 'A', code: 'SM001', subDomain: 'S', domain: 'D' }]
      ])
      const result = buildServiceModules(map)
      expect(result[0].annotationCategory).toBe('info')
    })

    it('未提供 annotationContent 时默认为空字符串', () => {
      const map = new Map([
        ['SM001', { name: 'A', code: 'SM001', subDomain: 'S', domain: 'D', annotationCategory: 'warn' }]
      ])
      const result = buildServiceModules(map)
      expect(result[0].annotationContent).toBe('')
      expect(result[0].annotationCategory).toBe('warn')
    })

    it('业务对象信息在 buildServiceModules 中不被输出 (该函数只关注 5 字段)', () => {
      const map = new Map([
        ['SM001', {
          name: 'A',
          code: 'SM001',
          subDomain: 'S',
          domain: 'D',
          businessObjects: [{ id: 'bo1' }]
        }]
      ])
      const result = buildServiceModules(map)
      expect(result[0].businessObjects).toBeUndefined()
    })
  })

  describe('buildDomainProducts', () => {
    it('空 Map 应返回空数组', () => {
      expect(buildDomainProducts(new Map())).toEqual([])
    })

    it('单 domain 单 subDomain 单 serviceModule 应正确转换', () => {
      const hierarchy = new Map([
        ['供应链云', {
          subDomains: new Map([
            ['采购', {
              serviceModules: [
                { name: '采购管理', code: 'SM001', businessObjects: [{ id: 'bo1' }] }
              ]
            }]
          ])
        }]
      ])
      const result = buildDomainProducts(hierarchy)
      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        name: '供应链云',
        modules: [
          {
            name: '采购',
            submodules: [
              {
                name: '采购管理',
                code: 'SM001',
                businessObjects: [{ id: 'bo1' }]
              }
            ]
          }
        ]
      })
    })

    it('单 domain 多个 subDomain 应保留所有 subDomain', () => {
      const hierarchy = new Map([
        ['供应链云', {
          subDomains: new Map([
            ['采购', { serviceModules: [{ name: '采购管理', code: 'SM001' }] }],
            ['库存', { serviceModules: [{ name: '库存管理', code: 'SM002' }] }]
          ])
        }]
      ])
      const result = buildDomainProducts(hierarchy)
      expect(result).toHaveLength(1)
      expect(result[0].modules).toHaveLength(2)
      expect(result[0].modules.map(m => m.name)).toEqual(['采购', '库存'])
    })

    it('多 domain 应输出多个 domainProduct', () => {
      const hierarchy = new Map([
        ['供应链云', {
          subDomains: new Map([
            ['采购', { serviceModules: [{ name: '采购管理', code: 'SM001' }] }]
          ])
        }],
        ['财务云', {
          subDomains: new Map([
            ['总账', { serviceModules: [{ name: '总账管理', code: 'SM002' }] }]
          ])
        }]
      ])
      const result = buildDomainProducts(hierarchy)
      expect(result).toHaveLength(2)
      expect(result.map(d => d.name)).toEqual(['供应链云', '财务云'])
    })

    it('businessObjects 缺失时应默认为空数组', () => {
      const hierarchy = new Map([
        ['D', {
          subDomains: new Map([
            ['S', { serviceModules: [{ name: 'm', code: 'm1' }] }]
          ])
        }]
      ])
      const result = buildDomainProducts(hierarchy)
      expect(result[0].modules[0].submodules[0].businessObjects).toEqual([])
    })

    it('嵌套层级: domain -> subDomain -> multiple serviceModules', () => {
      const hierarchy = new Map([
        ['D1', {
          subDomains: new Map([
            ['S1', {
              serviceModules: [
                { name: 'm1', code: 'c1', businessObjects: [] },
                { name: 'm2', code: 'c2', businessObjects: [{ id: 'b1' }] }
              ]
            }]
          ])
        }]
      ])
      const result = buildDomainProducts(hierarchy)
      expect(result[0].modules[0].submodules).toHaveLength(2)
      expect(result[0].modules[0].submodules[0].code).toBe('c1')
      expect(result[0].modules[0].submodules[1].code).toBe('c2')
    })
  })

  describe('buildPreviewData', () => {
    it('空对象应返回所有字段为 undefined 的对象', () => {
      const result = buildPreviewData({})
      expect(result).toEqual({
        businessObjects: undefined,
        serviceModules: undefined,
        relationships: undefined,
        serviceModuleRelationships: undefined,
        domainProducts: undefined
      })
    })

    it('完整参数应原样返回所有字段', () => {
      const params = {
        businessObjects: [{ id: 'bo1' }],
        serviceModules: [{ code: 'SM001' }],
        relationships: [{ id: 'r1' }],
        serviceModuleRelationships: [{ id: 'smr1' }],
        domainProducts: [{ name: 'D' }]
      }
      expect(buildPreviewData(params)).toEqual(params)
    })

    it('只传部分参数时, 未传字段为 undefined', () => {
      const result = buildPreviewData({ businessObjects: [{ id: 'bo1' }] })
      expect(result.businessObjects).toEqual([{ id: 'bo1' }])
      expect(result.serviceModules).toBeUndefined()
      expect(result.relationships).toBeUndefined()
      expect(result.serviceModuleRelationships).toBeUndefined()
      expect(result.domainProducts).toBeUndefined()
    })

    it('数组应保持引用不变', () => {
      const arr = [{ id: 'bo1' }]
      const result = buildPreviewData({ businessObjects: arr })
      expect(result.businessObjects).toBe(arr)
    })

    it('null 参数应原样保留', () => {
      const result = buildPreviewData({ businessObjects: null })
      expect(result.businessObjects).toBeNull()
    })
  })

  describe('extractSubDomains', () => {
    it('空数组应返回空数组', () => {
      expect(extractSubDomains([])).toEqual([])
    })

    it('null 输入应返回空数组', () => {
      expect(extractSubDomains(null)).toEqual([])
    })

    it('undefined 输入应返回空数组', () => {
      expect(extractSubDomains(undefined)).toEqual([])
    })

    it('单 subDomain 应返回 ["subName"]', () => {
      const domainProducts = [
        { name: 'D1', modules: [{ name: '采购', submodules: [] }] }
      ]
      expect(extractSubDomains(domainProducts)).toEqual(['采购'])
    })

    it('多 subDomain 应返回去重后的子领域列表', () => {
      const domainProducts = [
        { name: 'D1', modules: [{ name: '采购' }, { name: '库存' }] },
        { name: 'D2', modules: [{ name: '总账' }] }
      ]
      const result = extractSubDomains(domainProducts)
      expect(result).toHaveLength(3)
      expect(result).toEqual(expect.arrayContaining(['采购', '库存', '总账']))
    })

    it('重复的 subDomain 名应被去重', () => {
      const domainProducts = [
        { name: 'D1', modules: [{ name: '采购' }] },
        { name: 'D2', modules: [{ name: '采购' }] }
      ]
      expect(extractSubDomains(domainProducts)).toEqual(['采购'])
    })

    it('domain 缺少 modules 字段时不应抛错', () => {
      const domainProducts = [
        { name: 'D1' /* no modules */ },
        { name: 'D2', modules: [{ name: 'S1' }] }
      ]
      expect(extractSubDomains(domainProducts)).toEqual(['S1'])
    })
  })
})
