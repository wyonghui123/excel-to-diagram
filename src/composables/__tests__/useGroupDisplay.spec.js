import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGroupDisplay } from '../useGroupDisplay'

describe('useGroupDisplay', () => {
  function setup(colorMapping) {
    setActivePinia(createPinia())
    return useGroupDisplay(colorMapping)
  }

  it('getContainerName 解析对象为 "名称 (编码)"', () => {
    const { getContainerName } = setup()
    expect(getContainerName({ name: '库存', elementCode: 'STK' })).toBe('库存 (STK)')
    expect(getContainerName({ title: '库存' })).toBe('库存')
  })

  it('getGroupTypeLabel 返回中文标签', () => {
    const { getGroupTypeLabel } = setup()
    expect(getGroupTypeLabel('domain')).toBe('领域')
    expect(getGroupTypeLabel('custom')).toBe('自定义')
  })

  it('getElkGroupHint 返回提示', () => {
    const { getElkGroupHint } = setup()
    expect(getElkGroupHint('inner')).toContain('无关系')
  })

  it('getNodeColor 按 colorMapping 优先返回', () => {
    const { getNodeColor } = setup({ '库存': '#ff0000' })
    const containers = [{
      id: 'c1', name: '库存', domain: '库存',
      nodes: [{ id: 'N1', code: 'N1', name: '库存节点' }]
    }]
    expect(getNodeColor('N1', containers)).toBe('#ff0000')
  })
})