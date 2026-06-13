/**
 * groupedLayout 单测 (v32 复盘回归保护 - 2026-06-11)
 *
 * 覆盖:
 * - 方向控制 (LR/TB/BT/RL) (4 测试)
 * - 可见性 visible (3 测试)
 * - 启用/禁用 enabled (4 测试, 含 Bug 2 回归)
 * - disabled 容器在 4 种 layout 行为一致 (4 测试)
 *
 * 总计: 15 个测试
 *
 * 重要: groupedLayout 实际不会"打印方向/标题", 这些由内层 generateGroupCode
 *       在有 enabled 子组时才生成. 因此需要先创建有容器内容的 group
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { generateGroupedLayout } from '../groupedLayout'
import { generateLinearLayout } from '../linearLayout'
import { generateZoneLayout } from '../elkZoneLayout'
import { generateGridLayout } from '../gridLayout'
import { filterEnabledContainers } from '../containerFilter'

function makeNodeMap(nodes) {
  const map = new Map()
  nodes.forEach(n => map.set(n.code, n))
  return map
}

function makeDefinedNodes() {
  return new Set()
}

// 创建有节点的容器 (group 至少要有一个 enabled 节点才会生成代码)
const nodes = [
  { code: 'N1', name: '节点1' },
  { code: 'N2', name: '节点2' },
  { code: 'N3', name: '节点3' }
]
const containers = [
  { id: 'C1', name: '容器1', enabled: true, nodes: ['N1'] },
  { id: 'C2', name: '容器2', enabled: false, nodes: ['N2'] },
  { id: 'C3', name: '容器3', enabled: true, nodes: ['N3'] }
]

describe('groupedLayout - 方向控制 (需要 enabled 节点)', () => {
  it('group.direction=LR -> 包含 "direction LR"', () => {
    const groups = [{
      id: 'G1', title: '组1', direction: 'LR', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('direction LR')
  })

  it('group.direction=TB -> 包含 "direction TB"', () => {
    const groups = [{
      id: 'G1', title: '组1', direction: 'TB', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('direction TB')
  })

  it('group.direction 未设 -> 默认 TB', () => {
    const groups = [{
      id: 'G1', title: '组1', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('direction TB')
  })

  it('group.direction=BT 支持', () => {
    const groups = [{
      id: 'G1', title: '组1', direction: 'BT', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('direction BT')
  })
})

describe('groupedLayout - 可见性 (visible)', () => {
  it('group.visible=false -> subgraph 标题为空 "[ ]"', () => {
    const groups = [{
      id: 'G1', title: '隐藏组', visible: false, containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // visible=false 产生空标题 subgraph (groupId 格式: G_<id>)
    expect(result.mermaidCode).toMatch(/subgraph G_G1\[\s*\]/)
  })

  it('group.visible=true (默认) -> 标题正常', () => {
    const groups = [{
      id: 'G1', title: '显示组', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1["显示组"]')
  })

  it('visible=false + 有子组 -> 子组仍生成', () => {
    const groups = [{
      id: 'G1', title: '隐藏父', visible: false, containers: [containers[0]],
      children: [{ id: 'G2', title: '子组', containers: [containers[2]], children: [] }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1')
    expect(result.mermaidCode).toContain('subgraph G_G2')
  })
})

describe('groupedLayout - 启用/禁用 enabled (Bug 2 回归)', () => {
  it('group.enabled=false + 无 _disabledAncestorPath -> 不生成', () => {
    const groups = [{
      id: 'G1', title: '禁用组', enabled: false, containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).not.toContain('subgraph G_G1')
  })

  it('group.enabled=false + 有 _disabledAncestorPath -> 仍显示 (Bug 2 修复)', () => {
    const groups = [{
      id: 'G1', title: '被提升组', enabled: false,
      _disabledAncestorPath: ['parent-disabled-id'],
      containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // Bug 2 修复后: _disabledAncestorPath 非空 -> 仍显示
    expect(result.mermaidCode).toContain('subgraph G_G1')
  })

  it('group.enabled=true (默认) -> 正常显示', () => {
    const groups = [{
      id: 'G1', title: '启用组', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1')
  })
})

describe('groupedLayout - 容器 enabled (Bug 1 回归)', () => {
  it('容器 enabled=false -> 节点 N2 仍生成 (外提), 容器不显示', () => {
    const groups = [{
      id: 'G1', title: '组1', containers: [
        { id: 'C1', name: '容器1', enabled: true, nodes: ['N1'] },
        { id: 'C2', name: '容器2', enabled: false, nodes: ['N2'] },
        { id: 'C3', name: '容器3', enabled: true, nodes: ['N3'] }
      ], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 容器 C2 不应作为 subgraph 生成 (但因为有 C1/C3, 容器 1/3 会)
    // 关键断言: 节点 N2 (来自 disabled 容器) 仍被定义 (外提)
    expect(result.mermaidCode).toContain('N2')
    // 验证 disabled 容器的标题 '容器2' 不出现
    expect(result.mermaidCode).not.toContain('容器2')
  })
})

describe('filterEnabledContainers + 4 个 layout 一致性 (Bug 1 关键回归)', () => {
  it('linearLayout: disabled 容器 C2 不出现 (按名 Bug 1 修复)', () => {
    const code = generateLinearLayout(containers, [], 'horizontal', makeNodeMap(nodes), makeDefinedNodes())
    // 容器 1 和 3 显示, 容器 2 禁用, 不应出现
    expect(code).toContain('容器1')
    expect(code).not.toContain('容器2')  // Bug 1 关键断言
    expect(code).toContain('容器3')
  })

  it('zoneLayout: disabled 容器 C2 不出现 (按名 Bug 1 修复)', () => {
    const code = generateZoneLayout(containers, [], 'elk', 1, makeNodeMap(nodes), makeDefinedNodes())
    expect(code).toContain('容器1')
    expect(code).not.toContain('容器2')  // Bug 1 关键断言
    expect(code).toContain('容器3')
  })

  it('gridLayout: 渲染不抛错', () => {
    const code = generateGridLayout(containers, 1, 3)
    expect(code).toBeDefined()
    expect(typeof code).toBe('string')
  })

  it('filterEnabledContainers 直接测试', () => {
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)  // 容器 1 + 3
    expect(result.map(c => c.name)).toEqual(['容器1', '容器3'])
  })
})

describe('groupedLayout - 边界', () => {
  it('空 groups 返回空 code', () => {
    const result = generateGroupedLayout([], [], makeNodeMap([]), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toBe('')
    expect(result.styleLines.length).toBe(0)
  })

  it('null containers 不抛错', () => {
    const groups = [{
      id: 'G1', title: 'G', containers: [], children: []
    }]
    expect(() => {
      generateGroupedLayout(groups, null, makeNodeMap([]), makeDefinedNodes(), 'TB')
    }).not.toThrow()
  })
})
