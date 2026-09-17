import { describe, it, expect } from 'vitest'
import {
  extractGroupStates,
  applyGroupStates
} from '@/services/groupModel/layoutPanelAdapter.js'
import { applyDefaultExpandByScope, isSubtreeInScope } from '@/services/expandLevel.js'

/**
 * 折叠状态保持回归测试 (2026-08-09)
 *
 * 用户场景: 双击展开"采购供应"到服务模块 → 切换"区分/不区分业务对象"(centerScopeHighlight)
 *   → 采购供应被折叠回去 (回归)。
 *
 * 根因: EmbeddedChartView.layoutControlConfig computed 在 centerScopeHighlight 浅更新后重算,
 *   若 groupManualSet 未生效, 会对范围外分组套用 applyDefaultExpandByScope (折叠到子领域),
 *   覆盖用户手动展开状态。本测试锁定该不变式:
 *   用户手动展开 (groupManualSet=true) 时, 必须保留 per-group collapsed, 不得套用范围默认折叠。
 */

// 渲染源 unified 树: 采购供应(SD_MM) 默认折叠到子领域 (SM 聚合节点)
function buildUnifiedTree() {
  return [
    {
      id: 'G_D_SCM', elementCode: 'SCM', groupType: 'domain', title: '供应链云', collapsed: false,
      children: [
        {
          id: 'G_SD_MM', elementCode: 'SD_MM', groupType: 'subDomain', title: '采购供应', collapsed: true,
          children: [
            { id: 'G_SM_PUM', elementCode: 'SM_PUM', groupType: 'serviceModule', title: '采购管理', collapsed: true },
            { id: 'G_SM_INV', elementCode: 'SM_INV', groupType: 'serviceModule', title: '库存管理', collapsed: true }
          ]
        }
      ]
    }
  ]
}

// 用户(双击展开后)面板树: 采购供应已展开到服务模块 (collapsed=false)
function buildUserExpandedTree() {
  return [
    {
      elementCode: 'SCM', groupType: 'domain', collapsed: false,
      children: [
        {
          elementCode: 'SD_MM', groupType: 'subDomain', collapsed: false,
          children: [
            { elementCode: 'SM_PUM', groupType: 'serviceModule', collapsed: false },
            { elementCode: 'SM_INV', groupType: 'serviceModule', collapsed: false }
          ]
        }
      ]
    }
  ]
}

// 复刻 EmbeddedChartView.layoutControlConfig computed 的合并分支 (含 groupManualSet 判断)
function mergeWithStates(unified, userConfig, { groupManualSet, centerScope }) {
  const userStates = extractGroupStates(userConfig)
  const merged = JSON.parse(JSON.stringify(unified))
  if (userStates.size > 0) {
    applyGroupStates(merged, userStates)
  }
  if (groupManualSet) {
    // 用户手动调整过 → 尊重 per-group collapsed, 不套用任何默认展开
  } else if (centerScope && centerScope.length > 0) {
    const scopeCodeSet = new Set(centerScope)
    applyDefaultExpandByScope(merged, (g) => isSubtreeInScope(g, scopeCodeSet))
  }
  return merged
}

const findGroup = (list, code) => {
  for (const g of list) {
    if (!g || typeof g !== 'object') continue
    if (g.elementCode === code || g.id === code) return g
    const r = findGroup(g.children || [], code)
    if (r) return r
    const r2 = findGroup((g.containers || []).filter(c => c && typeof c === 'object'), code)
    if (r2) return r2
  }
  return null
}

describe('双击展开保持 / 切 centerScopeHighlight 不折叠', () => {
  it('groupManualSet=true 时保留用户手动展开的采购供应 (范围外分组不被默认折叠)', () => {
    // 采购供应(SD_MM) 在 SCP 范围外, 若套用范围默认折叠会被折叠到子领域(SM 聚合)
    const merged = mergeWithStates(buildUnifiedTree(), buildUserExpandedTree(), {
      groupManualSet: true,
      centerScope: ['SCP'] // 采购供应不在 SCP 范围内
    })
    const sd = findGroup(merged, 'SD_MM')
    const smPum = findGroup(merged, 'SM_PUM')
    expect(sd.collapsed).toBe(false)
    expect(smPum.collapsed).toBe(false) // 服务模块仍展开 (未被折叠回聚合节点)
  })

  it('groupManualSet=false 且范围外时会被范围默认折叠 (证明 groupManualSet 跳过的必要性)', () => {
    // 树中必须存在范围内分组(SCP)使 applyDefaultExpandByScope 的 hasScope=true 命中,
    // 否则其早退不折叠 (与 2026-08-09 真实场景一致: 存在 SCP 范围, 采购供应属范围外).
    const tree = [
      ...buildUnifiedTree(),
      { id: 'G_SD_SCP', elementCode: 'SCP', groupType: 'subDomain', title: '供应链计划', collapsed: false, children: [] }
    ]
    const user = [
      ...buildUserExpandedTree(),
      { elementCode: 'SCP', groupType: 'subDomain', collapsed: false, children: [] }
    ]
    const merged = mergeWithStates(tree, user, {
      groupManualSet: false,
      centerScope: ['SCP']
    })
    const sd = findGroup(merged, 'SD_MM')
    const smPum = findGroup(merged, 'SM_PUM')
    // 范围外分组默认折叠到子领域(targetLevel=1) → 子领域自身及更深全部折叠为单个节点
    // (即用户看到的"采购供应折叠回去", 全部收缩成一个子领域聚合节点)
    expect(sd.collapsed).toBe(true)
    expect(smPum.collapsed).toBe(true)
  })

  it('extractGroupStates 保留 collapsed 状态 (跨管道合并不丢失)', () => {
    const states = extractGroupStates(buildUserExpandedTree())
    expect(states.get('SD_MM').collapsed).toBe(false)
    expect(states.get('SM_PUM').collapsed).toBe(false)
    expect(states.get('SM_INV').collapsed).toBe(false)
  })

  it('applyGroupStates 回填 collapsed 到 merged 树', () => {
    const merged = JSON.parse(JSON.stringify(buildUnifiedTree()))
    const states = extractGroupStates(buildUserExpandedTree())
    applyGroupStates(merged, states)
    expect(findGroup(merged, 'SD_MM').collapsed).toBe(false)
    expect(findGroup(merged, 'SM_PUM').collapsed).toBe(false)
    expect(findGroup(merged, 'SM_INV').collapsed).toBe(false)
  })
})
