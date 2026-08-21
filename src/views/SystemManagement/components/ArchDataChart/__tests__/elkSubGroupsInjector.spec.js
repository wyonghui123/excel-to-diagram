/**
 * elkSubGroupsInjector.spec - 面板"无关系/有关系"系统自动分组注入渲染树
 *
 * [ELK-GROUP 2026-08-12] 覆盖:
 *   - 面板树 ELK 子分组(_elkGroup=inner/boundary) 注入渲染树服务模块下
 *   - enabled/visible 状态透传 (面板切换驱动图表分组)
 *   - 兼容 containers[].nodes 与 directNodes 两种 BO 编码收集形态
 *   - 未覆盖 BO 保留在原 directNodes (防御: 面板与投影编码不一致时不丢节点)
 */
import { describe, it, expect } from 'vitest'
import { injectElkSubGroups } from '../elkSubGroupsInjector.js'

// 渲染树: 服务模块仅存扁平 directNodes (deriveLayoutGroups 输出形态)
function renderTree() {
  return [
    {
      id: 'D_SCM', elementCode: 'SC', groupType: 'domain', children: [
        { id: 'SD_SCP', elementCode: 'SCP', groupType: 'subDomain', children: [
          { id: 'SM_DP', elementCode: 'DP', groupType: 'serviceModule', directNodes: ['PO', 'DP', 'RR', 'EXTRA'], children: [] }
        ] }
      ]
    }
  ]
}

// 面板树: 服务模块 children 含 ELK 子分组 (buildBusinessObjectGroups 输出形态)
function panelTree({ innerVisible = false, innerEnabled = true, boundaryVisible = true, boundaryEnabled = true } = {}) {
  return [
    {
      id: 'P_D_SCM', elementCode: 'SC', groupType: 'domain', children: [
        { id: 'P_SD_SCP', elementCode: 'SCP', groupType: 'subDomain', children: [
          {
            id: 'P_SM_DP', elementCode: 'DP', groupType: 'serviceModule',
            children: [
              {
                id: 'P_SM_DP_inner', elementCode: 'DP_inner', title: '无关系', _elkGroup: 'inner',
                enabled: innerEnabled, visible: innerVisible,
                containers: [
                  { id: 'C_PO', nodes: ['PO'] },
                  { id: 'C_DP', nodes: ['DP'] }
                ]
              },
              {
                id: 'P_SM_DP_boundary', elementCode: 'DP_boundary', title: '有关系', _elkGroup: 'boundary',
                enabled: boundaryEnabled, visible: boundaryVisible,
                directNodes: ['RR']   // 渲染格式 (updateLayoutControlConfig 写回 store 后)
              }
            ]
          }
        ] }
      ]
    }
  ]
}

function findSm(merged) {
  return merged[0].children[0].children[0]
}

describe('injectElkSubGroups', () => {
  it('面板树 ELK 子分组注入渲染树服务模块下 (children=[inner,boundary], 覆盖 BO 移出 directNodes)', () => {
    const merged = renderTree()
    injectElkSubGroups(merged, panelTree())
    const sm = findSm(merged)
    expect(sm.children).toHaveLength(2)
    const inner = sm.children.find(c => c._elkGroup === 'inner')
    const boundary = sm.children.find(c => c._elkGroup === 'boundary')
    expect(inner).toBeTruthy()
    expect(boundary).toBeTruthy()
    expect(inner.groupType).toBe('custom')
    expect(inner.directNodes).toEqual(['PO', 'DP'])
    expect(boundary.directNodes).toEqual(['RR'])
    // 被 ELK 覆盖的 BO 移出 directNodes, 未覆盖的 EXTRA 保留
    expect(sm.directNodes).toEqual(['EXTRA'])
  })

  it('enabled/visible 状态从面板透传 (驱动面板切换)', () => {
    const merged = renderTree()
    injectElkSubGroups(merged, panelTree({ innerVisible: false, innerEnabled: false }))
    const sm = findSm(merged)
    const inner = sm.children.find(c => c._elkGroup === 'inner')
    expect(inner.enabled).toBe(false)
    expect(inner.visible).toBe(false)
  })

  it('enabled 缺省视为 true (undefined → true)', () => {
    const merged = renderTree()
    const panel = panelTree()
    // 移除 inner 的 enabled, 模拟面板未设置
    delete panel[0].children[0].children[0].children[0].enabled
    injectElkSubGroups(merged, panel)
    const inner = findSm(merged).children.find(c => c._elkGroup === 'inner')
    expect(inner.enabled).toBe(true)
  })

  it('panelGroups 为空 → mergedGroups 原样返回', () => {
    const merged = renderTree()
    const out = injectElkSubGroups(merged, [])
    expect(out).toBe(merged)
    expect(findSm(merged).children).toHaveLength(0)
  })

  it('面板无 ELK 子分组 → mergedGroups 不变 (children 不新增)', () => {
    const merged = renderTree()
    const panel = [
      { elementCode: 'SC', groupType: 'domain', children: [
        { elementCode: 'SCP', groupType: 'subDomain', children: [
          { elementCode: 'DP', groupType: 'serviceModule', children: [] } // 无 ELK 子分组
        ] }
      ] }
    ]
    injectElkSubGroups(merged, panel)
    expect(findSm(merged).children).toHaveLength(0)
    expect(findSm(merged).directNodes).toEqual(['PO', 'DP', 'RR', 'EXTRA'])
  })

  it('仅 inner 存在时只注入 inner, boundary 不注入', () => {
    const merged = renderTree()
    const panel = panelTree()
    // 移除 boundary 子分组
    const smChildren = panel[0].children[0].children[0].children
    smChildren.splice(smChildren.findIndex(c => c._elkGroup === 'boundary'), 1)
    injectElkSubGroups(merged, panel)
    const sm = findSm(merged)
    expect(sm.children).toHaveLength(1)
    expect(sm.children[0]._elkGroup).toBe('inner')
  })

  it('[FIX 2026-08-19] SM 下已有 ELK 兄弟分组时, 保留用户自定义分组不被覆盖', () => {
    // 渲染树 SM.children 含用户新建的自定义分组 (applyContainerMembership 补入)
    const merged = renderTree()
    findSm(merged).children = [
      { id: 'grp_custom', elementCode: 'grp_custom', groupType: 'custom', directNodes: ['EXTRA'], containers: [], children: [] }
    ]
    injectElkSubGroups(merged, panelTree())
    const sm = findSm(merged)
    const ids = sm.children.map(c => c.id || c.elementCode)
    // ELK 注入 + 用户自定义分组都保留 (原 sm.children=children 会覆盖掉用户分组 → 不展示)
    expect(ids).toContain('P_SM_DP_inner')
    expect(ids).toContain('P_SM_DP_boundary')
    expect(ids).toContain('grp_custom')
    expect(sm.children).toHaveLength(3)
  })
})
