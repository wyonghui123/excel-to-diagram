
import { describe, it, expect } from 'vitest'
import { useMermaidDataMap } from '@/composables/useMermaid/dataMap/useMermaidDataMap.js'

describe('useMermaidDataMap.buildObjectToModuleMap - v34 颜色修复', () => {
  it('应挂载 serviceModule/serviceModuleName (供 colorGroupBy=serviceModule 使用)', () => {
    const { buildObjectToModuleMap } = useMermaidDataMap()
    const data = {
      businessObjects: [
        { code: 'BO_A', name: 'A', serviceModule: 'SM001', serviceModuleName: '订单模块' },
        { code: 'BO_B', name: 'B', serviceModule: 'SM002', serviceModuleName: '库存模块' },
        { code: 'BO_C', name: 'C', serviceModule: 'SM003', serviceModuleName: '财务模块' }
      ],
      domainProducts: [
        {
          name: '采购域',
          businessObjects: [],
          modules: [
            {
              name: '采购管理',
              submodules: [
                { name: '订单', businessObjects: [{ code: 'BO_A', name: 'A' }] },
                { name: '库存', businessObjects: [{ code: 'BO_B', name: 'B' }] }
              ]
            }
          ]
        },
        {
          name: '财务域',
          businessObjects: [{ code: 'BO_C', name: 'C' }]
        }
      ]
    }
    const map = buildObjectToModuleMap(data)
    expect(map.get('BO_A').serviceModule).toBe('SM001')
    expect(map.get('BO_A').serviceModuleName).toBe('订单模块')
    expect(map.get('BO_B').serviceModule).toBe('SM002')
    expect(map.get('BO_C').serviceModule).toBe('SM003')
    expect(map.get('BO_C').serviceModuleName).toBe('财务模块')
  })

  it('业务对象无 serviceModule 字段时不应崩, 应给空字符串', () => {
    const { buildObjectToModuleMap } = useMermaidDataMap()
    const data = {
      businessObjects: [{ code: 'BO_X', name: 'X' }],
      domainProducts: [{
        name: '域',
        businessObjects: [{ code: 'BO_X', name: 'X' }]
      }]
    }
    const map = buildObjectToModuleMap(data)
    expect(map.get('BO_X').serviceModule).toBeUndefined()
    expect(map.get('BO_X').serviceModuleName).toBeUndefined()
  })
})
