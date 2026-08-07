/**
 * useViewTemplates 单测 (FR-005 视图模板 + 多态操作, 2026-08-05 v2.1)
 *
 * 覆盖:
 * - allEnabled: 所有 enabled=true
 * - onlyServiceModules: BO 图隐藏 BO 叶节点, 保留 serviceModule 分组
 * - onlyServiceModules: SM 图无副作用 (SM 容器不被隐藏)
 * - isBusinessObjectLeaf 判定
 * - 多态操作: setSubtreeEnabled / collapseToNode / showDescendantsOnly
 */
import { describe, it, expect } from 'vitest'
import { applyViewTemplate, isBusinessObjectLeaf, setSubtreeEnabled, collapseToNode, showDescendantsOnly } from '../useViewTemplates'

// BO 图结构: domain → subDomain → serviceModule → [inner/boundary → BO 叶 container]
function makeBoChartGroups() {
  return [
    {
      id: 'D1', title: '采购云', groupType: 'domain', enabled: true,
      children: [
        {
          id: 'SD1', title: '采购管理', groupType: 'subDomain', enabled: true,
          children: [
            {
              id: 'SM1', title: '采购管理模块', groupType: 'serviceModule', enabled: true,
              children: [],
              containers: [
                { id: 'bo1', elementCode: 'BO1', isVirtual: true, groupType: 'custom', enabled: true, nodes: ['BO1'] },
                { id: 'bo2', elementCode: 'BO2', isVirtual: true, groupType: 'custom', enabled: true, nodes: ['BO2'] }
              ]
            }
          ]
        }
      ]
    }
  ]
}

// SM 图结构: domain → subDomain → SM container (groupType='serviceModule')
function makeSmChartGroups() {
  return [
    {
      id: 'D1', title: '采购云', groupType: 'domain', enabled: true,
      children: [
        {
          id: 'SD1', title: '采购管理', groupType: 'subDomain', enabled: true,
          containers: [
            { id: 'sm1', elementCode: 'SM1', groupType: 'serviceModule', elementRef: { type: 'SERVICE_MODULE', code: 'SM1' }, enabled: true }
          ]
        }
      ]
    }
  ]
}

describe('isBusinessObjectLeaf', () => {
  it('BO 虚拟容器 (isVirtual=true) → true', () => {
    expect(isBusinessObjectLeaf({ isVirtual: true, elementCode: 'BO1' })).toBe(true)
  })

  it('elementRef.type=BUSINESS_OBJECT → true', () => {
    expect(isBusinessObjectLeaf({ elementRef: { type: 'BUSINESS_OBJECT' } })).toBe(true)
  })

  it('serviceModule 分组/容器 → false', () => {
    expect(isBusinessObjectLeaf({ groupType: 'serviceModule' })).toBe(false)
    expect(isBusinessObjectLeaf({ elementRef: { type: 'SERVICE_MODULE' } })).toBe(false)
  })

  it('有子树的非叶分组 → false', () => {
    expect(isBusinessObjectLeaf({ groupType: 'domain', children: [{}] })).toBe(false)
  })
})

describe('applyViewTemplate - allEnabled', () => {
  it('恢复所有 enabled=true', () => {
    const groups = [{
      id: 'D1', groupType: 'domain', enabled: true,
      children: [{ id: 'SD1', groupType: 'subDomain', enabled: false }]
    }]
    applyViewTemplate(groups, 'allEnabled')
    expect(groups[0].enabled).toBe(true)
    expect(groups[0].children[0].enabled).toBe(true)
  })
})

describe('applyViewTemplate - onlyServiceModules (BO 图)', () => {
  it('隐藏 BO 叶节点, 保留 serviceModule 分组', () => {
    const groups = makeBoChartGroups()
    applyViewTemplate(groups, 'onlyServiceModules')
    const sm = groups[0].children[0].children[0]
    // serviceModule 分组保留
    expect(sm.enabled).toBe(true)
    // BO 叶节点被隐藏
    expect(sm.containers[0].enabled).toBe(false)
    expect(sm.containers[1].enabled).toBe(false)
  })
})

describe('applyViewTemplate - onlyServiceModules (SM 图)', () => {
  it('SM 容器不被隐藏 (无副作用)', () => {
    const groups = makeSmChartGroups()
    applyViewTemplate(groups, 'onlyServiceModules')
    const sm = groups[0].children[0].containers[0]
    expect(sm.enabled).toBe(true)
  })
})

describe('setSubtreeEnabled - 级联启用/禁用', () => {
  it('禁用父分组 → 子孙全部禁用', () => {
    const groups = makeBoChartGroups()
    const domain = groups[0]
    const count = setSubtreeEnabled(domain, false)
    expect(domain.enabled).toBe(false)
    expect(domain.children[0].enabled).toBe(false)
    const sm = domain.children[0].children[0]
    expect(sm.enabled).toBe(false)
    expect(sm.containers[0].enabled).toBe(false)
    expect(sm.containers[1].enabled).toBe(false)
    // 至少 父 + 子域 + SM + 2 BO = 5 个节点状态变化
    expect(count).toBeGreaterThanOrEqual(5)
  })

  it('启用父分组 → 子孙全部启用', () => {
    const groups = makeBoChartGroups()
    setSubtreeEnabled(groups[0], false)
    setSubtreeEnabled(groups[0], true)
    expect(groups[0].enabled).toBe(true)
    expect(groups[0].children[0].children[0].containers[0].enabled).toBe(true)
  })
})

describe('collapseToNode - 折叠为节点 (自身启用+子孙禁用→自动上提)', () => {
  it('自身启用, 全部子孙禁用', () => {
    const groups = makeBoChartGroups()
    const domain = groups[0]
    collapseToNode(domain)
    expect(domain.enabled).toBe(true)
    expect(domain.children[0].enabled).toBe(false)
    expect(domain.children[0].children[0].containers[0].enabled).toBe(false)
  })
})

describe('showDescendantsOnly - 仅显示子孙 (自身禁用+子孙启用)', () => {
  it('自身禁用, 全部子孙启用', () => {
    const groups = makeBoChartGroups()
    const domain = groups[0]
    setSubtreeEnabled(domain, false) // 先全部禁用
    showDescendantsOnly(domain)
    expect(domain.enabled).toBe(false)
    expect(domain.children[0].enabled).toBe(true)
    expect(domain.children[0].children[0].containers[0].enabled).toBe(true)
  })
})