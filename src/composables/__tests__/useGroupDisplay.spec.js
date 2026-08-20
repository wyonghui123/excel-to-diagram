import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGroupDisplay } from '../useGroupDisplay'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

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

  // [FOLD-COLOR 2026-08-20] 分组层级比颜色分组层级更粗 → 中性灰, 不取 hashColor 的任意色(红).
  //   用同一 pinia, 保证 store.colorGroupBy 与 useGroupDisplay 读到的状态一致.
  function setupWithGroupBy(colorGroupBy) {
    setActivePinia(createPinia())
    const store = useDiagramConfigStore()
    store.colorGroupBy = colorGroupBy
    return { display: useGroupDisplay({}), store }
  }

  it('colorGroupBy=subDomain 时领域分组色点为中性灰(不是 hashColor 任意色)', () => {
    const { display } = setupWithGroupBy('subDomain')
    const domainGroup = { groupType: 'domain', title: '供应链云' }
    const info = display.getGroupColor(domainGroup)
    expect(info.color).toBe('#808080')
    expect(info.isCenter).toBe(false)
  })

  it('colorGroupBy=serviceModule 时领域/子领域分组色点为中性灰', () => {
    const { display } = setupWithGroupBy('serviceModule')
    expect(display.getGroupColor({ groupType: 'domain', title: '供应链云' }).color).toBe('#808080')
    expect(display.getGroupColor({ groupType: 'subDomain', title: '供应链计划' }).color).toBe('#808080')
  })

  it('colorGroupBy 与分组层级相同时保留分组色(非中性灰), 比分组层级更粗才中性灰', () => {
    const { display } = setupWithGroupBy('subDomain')
    // 子领域分组 + subDomain 同位 → 不触发中性灰, 回退 hashColor (非 #808080)
    expect(display.getGroupColor({ groupType: 'subDomain', title: '库存' }).color).not.toBe('#808080')
    // 领域分组(0) < subDomain(1) → 中性灰 (不因 title 命中子领域色而变彩)
    expect(display.getGroupColor({ groupType: 'domain', title: '供应链计划' }).color).toBe('#808080')
  })
})