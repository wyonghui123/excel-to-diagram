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
import { generateGroupedLayout, getLiftedParentPathMap, buildLayoutHelperEdges } from '../groupedLayout'
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
  it('group.visible=false -> 整棵子树不渲染 (无 subgraph 输出)', () => {
    const groups = [{
      id: 'G1', title: '隐藏组', visible: false, containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // [VIS 2026-08-07] 修复: visible=false 跳过整棵子树, 不再输出空标题 subgraph
    expect(result.mermaidCode).not.toMatch(/subgraph G_G1/)
  })

  it('group.visible=true (默认) -> 标题正常', () => {
    const groups = [{
      id: 'G1', title: '显示组', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1["显示组"]')
  })

  it('visible=false + 有子组 -> 子组一并隐藏 (级联子树不渲染)', () => {
    const groups = [{
      id: 'G1', title: '隐藏父', visible: false, containers: [containers[0]],
      children: [{ id: 'G2', title: '子组', containers: [containers[2]], children: [] }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // [VIS 2026-08-07] 修复: 隐藏父领域 (如供应链云) 后其子领域 (如销售) 也应隐藏
    expect(result.mermaidCode).not.toMatch(/subgraph G_G1/)
    expect(result.mermaidCode).not.toMatch(/subgraph G_G2/)
  })

  it('父组 visible=true 但所有子组 hidden -> 父组空盒不渲染 (用户: 销售保留空容器)', () => {
    // 用户场景: 隐藏供应链云后, 销售子领域下的服务模块(销售管理)已隐藏,
    // 但销售子领域容器本身仍显示为空盒. 期望: 销售容器也应一并消失.
    const groups = [{
      id: 'SD_SM', title: '销售', visible: true, groupType: 'subDomain', containers: [],
      children: [{
        id: 'SM_OM', title: '销售管理', visible: false, groupType: 'serviceModule',
        directNodes: ['N1'], containers: [], children: []
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 子组(销售管理)已隐藏 → 父组(销售)无可见内容 → 不应渲染空盒 subgraph
    expect(result.mermaidCode).not.toMatch(/subgraph G_SD_SM/)
  })
})

describe('groupedLayout - 启用/禁用 enabled (Bug 2 回归)', () => {
  it('group.enabled=false + 无内容 (无 children/containers/directNodes) -> 不生成', () => {
    const groups = [{
      id: 'G1', title: '禁用空组', enabled: false, containers: [], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).not.toContain('subgraph G_G1')
  })

  it('group.enabled=false + 有 containers -> 组自身 subgraph 不生成, 容器内容打平渲染', () => {
    // [FIX 2026-08-04] disabled 分支职责: 打平子元素到当前层级.
    //   旧 bug: hasGroupContent 对 disabled 恒 false → 提前返回 → 容器内容也消失.
    //   修复后: 组自身 subgraph (G_G1[) 不生成, 但容器 subgraph (G_G1_C1) 生成并含节点.
    const groups = [{
      id: 'G1', title: '禁用组', enabled: false, containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 组自身 subgraph 不生成 (精确匹配, 不误伤 G_G1_C1)
    expect(result.mermaidCode).not.toContain('subgraph G_G1["')
    // 容器内容仍渲染 (打平到当前层级)
    expect(result.mermaidCode).toContain('N1')
  })

  it('group.enabled=false + 有 _disabledAncestorPath -> 容器内容仍显示', () => {
    const groups = [{
      id: 'G1', title: '被提升组', enabled: false,
      _disabledAncestorPath: ['parent-disabled-id'],
      containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // Bug 2 修复后: _disabledAncestorPath 非空 -> 容器内容仍显示
    expect(result.mermaidCode).toContain('N1')
  })

  it('group.enabled=true (默认) -> 正常显示', () => {
    const groups = [{
      id: 'G1', title: '启用组', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1')
  })

  it('group.enabled=false + 有 enabled children -> 子组仍生成 (Bug: 禁用供应链云后子领域消失)', () => {
    // 场景: SM 图禁用父域 "供应链云", 子领域仍 enabled=true.
    //   deriveLayoutGroups 输出: domain(enabled=false) → children: [subDomain(enabled=true, directNodes)]
    //   期望: 父域 subgraph 不生成, 子域 subgraph 生成并包含节点.
    const groups = [{
      id: 'D1', title: '禁用父域', enabled: false,
      containers: [], directNodes: undefined,
      children: [{
        id: 'S1', title: '子域', enabled: true,
        directNodes: ['N1', 'N2'], containers: [], children: []
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 父域 subgraph 不应生成 (disabled)
    expect(result.mermaidCode).not.toContain('subgraph G_D1')
    // 子域 subgraph 应该生成 (enabled, 被打平到顶层)
    expect(result.mermaidCode).toContain('subgraph G_S1')
    // 子域的节点应该生成
    expect(result.mermaidCode).toContain('N1')
    expect(result.mermaidCode).toContain('N2')
  })

  it('[FIX 2026-08-19] 禁用分组(directNodes)嵌套在启用父级内 -> 节点打平在父容器内不逃逸', () => {
    // 用户反馈: 库存管理禁用后子节点应还在采购供应容器内 (而非跑到父容器之外).
    // 结构: 父容器 G1(enabled) → 子分组 G2(disabled, directNodes=['N3'])
    // 期望: G1 subgraph 生成, N3 以缩进行渲染在 G1 内 (禁用分支打平到父容器层级).
    const groups = [{
      id: 'G1', title: '父容器', enabled: true, containers: [], directNodes: [],
      children: [{
        id: 'G2', title: '禁用组', enabled: false, containers: [], directNodes: ['N3'], children: []
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1')
    expect(result.mermaidCode).not.toContain('subgraph G_G2')
    // N3 渲染为缩进行 (位于 G_G1 内), 而非顶层无缩进
    expect(result.mermaidCode).toContain('  N3["节点3')
    expect(result.mermaidCode).not.toContain('\nN3[')
  })

  it('[FIX 2026-08-19] 禁用分组(enabled 后代)嵌套在启用父级内 -> 父级不被整体跳过 (hasGroupContent)', () => {
    // 原 bug: hasGroupContent 对 disabled 恒 false → 父级级联 false → 父级被整体跳过
    //   → 禁用子领域后整个图表塌缩. 修复: disabled 分组若有渲染后代视为有内容.
    // 结构: G1(enabled) → G2(disabled) → G3(enabled, directNodes=['N3'])
    // 期望: G1 与 G3 subgraph 均生成, G2 自身 subgraph 不生成.
    const groups = [{
      id: 'G1', title: '父域', enabled: true, containers: [], directNodes: [],
      children: [{
        id: 'G2', title: '禁用子域', enabled: false, containers: [], directNodes: [],
        children: [{
          id: 'G3', title: '启用子组', enabled: true, containers: [], directNodes: ['N3'], children: []
        }]
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1')
    expect(result.mermaidCode).not.toContain('subgraph G_G2')
    expect(result.mermaidCode).toContain('subgraph G_G3')
    expect(result.mermaidCode).toContain('N3')
  })

  it('[FIX 2026-08-06] 父容器 disabled 后被打平提升的子容器标题保持单行, 父名注册进 registry 供 tooltip', () => {
    // 场景: SM 图禁用父域 "供应链云", 子域 "供应链计划" 仍 enabled=true → 被打平提升到顶层.
    //   方案演进 (2026-08-06g): 标题改为单行 (只显示自身名 "供应链计划"), 父名称不再拼进标题
    //   (原 "供应链计划（供应链云）" 会被 formatContainerTitle 拆两行, 与 ELK 单行预留冲突
    //   → 后处理下移内容导致节点/子容器跑出容器盒, 已废弃). 父名称写入 registry,
    //   由 SVG 处理器 attachLiftedParentTooltips 转成悬停 tooltip.
    const groups = [{
      id: 'D_SCM', title: '供应链云', enabled: false,
      containers: [], directNodes: undefined,
      children: [{
        id: 'S_SCP', title: '供应链计划', enabled: true,
        directNodes: ['N1', 'N2'], containers: [], children: []
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 父域 subgraph 不生成 (disabled)
    expect(result.mermaidCode).not.toContain('subgraph G_D_SCM')
    // 子域 subgraph 标题为单行 (自身名), 不再拼父名
    expect(result.mermaidCode).toContain('subgraph G_S_SCP["供应链计划"]')
    // 父名称注册进 registry, 供 attachLiftedParentTooltips 挂 tooltip
    expect(getLiftedParentPathMap()).toHaveProperty('G_S_SCP', '供应链云')
    // 子域节点仍生成
    expect(result.mermaidCode).toContain('N1')
    expect(result.mermaidCode).toContain('N2')
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

  it('容器 visible=false -> 节点仍生成 (外提), 容器边框不显示 (LAYOUT 2026-08-04)', () => {
    const groups = [{
      id: 'G1', title: '组1', containers: [
        { id: 'C1', name: '容器1', enabled: true, visible: true, nodes: ['N1'] },
        { id: 'C2', name: '容器2', enabled: true, visible: false, nodes: ['N2'] }
      ], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // visible=false 的容器: 不生成 subgraph 边框, 节点 N2 打平渲染
    expect(result.mermaidCode).toContain('N2')
    expect(result.mermaidCode).not.toContain('容器2')
    // visible=true 的容器: 正常生成 subgraph
    expect(result.mermaidCode).toContain('容器1')
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

// [UPLIFT 2026-08-05] 上提语义 (FR-001/002) 回归保护: 取代显式 group.collapsed.
//   分组 enabled 且无任何可见子孙 → 自动上提为单个聚合节点 (COLLAPSE_<id>).
describe('groupedLayout - 上提 uplift', () => {
  it('group enabled 且无可见子孙 -> 上提为聚合节点, 子孙/容器不渲染', () => {
    const upliftGroup = {
      id: 'G1', title: '采购云', enabled: true,
      containers: [{ id: 'C1', name: '容器1', enabled: false, nodes: ['N1'] }],
      children: [{ id: 'G1C', title: '子域', enabled: false, containers: [containers[1]], children: [] }],
      directNodes: []
    }
    const result = generateGroupedLayout([upliftGroup], containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 上提聚合节点编码稳定
    expect(result.mermaidCode).toContain('COLLAPSE_G1')
    // 子孙节点文本不渲染
    expect(result.mermaidCode).not.toContain('节点1')
    expect(result.mermaidCode).not.toContain('节点2')
    // 不创建该组的 subgraph (容器)
    expect(result.mermaidCode).not.toContain('subgraph G_G1["')
  })

  it('group enabled 且有可见子孙 -> 正常渲染为容器, 不上提', () => {
    const groups = [{
      id: 'G1', title: '组1', direction: 'LR', containers: [containers[0]], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('direction LR')
    expect(result.mermaidCode).toContain('N1')
    expect(result.mermaidCode).not.toContain('COLLAPSE_')
  })

  it('[FIX 2026-08-19 修订] 空自定义分组(groupType=custom, 无内容)自动上提 → COLLAPSE 聚合节点', () => {
    // 用户新建的空自定义分组(末端叶子, 无任何 BO): 渲染空容器框没有视觉意义,
    //   统一上提为聚合节点 (与系统分组空内容行为一致). 拖入 BO 后自动变容器.
    const groups = [{
      id: 'grp_custom_1', title: '自定义分组A', groupType: 'custom', enabled: true,
      containers: [], children: [], directNodes: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_grp_custom_1')
    expect(result.mermaidCode).not.toContain('subgraph G_grp_custom_1["自定义分组A"]')
  })

  it('[FIX 2026-08-19] 空自定义分组显式折叠(collapsed=true) 上提为聚合节点 (尊重用户操作)', () => {
    const groups = [{
      id: 'grp_custom_2', title: '自定义分组B', groupType: 'custom', enabled: true, collapsed: true,
      containers: [], children: [], directNodes: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_grp_custom_2')
  })

  it('[FIX 2026-08-19 节点标题] 空自定义分组自动上提节点标题不带省略号, 显式折叠保留省略号', () => {
    // 空内容自动上提: 无可展开内容, 标题纯标题不带 "…" (省略号暗示"折叠容器可展开", 对空节点有误导)
    const empty = [{
      id: 'grp_noellipsis', title: '空白分组', groupType: 'custom', enabled: true,
      containers: [], children: [], directNodes: []
    }]
    const rEmpty = generateGroupedLayout(empty, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(rEmpty.mermaidCode).toMatch(/COLLAPSE_grp_noellipsis\["空白分组"\]/)
    expect(rEmpty.mermaidCode).not.toContain('空白分组…')
    // 显式折叠(collapsed=true) 的…省略: 表明有内容待展开 → 保留
    const folded = JSON.parse(JSON.stringify(empty[0]))
    folded.id = 'grp_ellipsis'; folded.title = '折叠分组'; folded.collapsed = true
    const rFolded = generateGroupedLayout([folded], containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(rFolded.mermaidCode).toMatch(/COLLAPSE_grp_ellipsis\["折叠分组…"\]/)
  })

  it('[FIX 2026-08-19 自定义分组着色] 容器形态用 group.style 填充色 (fill/stroke)', () => {
    const groups = [{
      id: 'grp_color_c', title: '彩色分组', groupType: 'custom', enabled: true,
      style: { fill: '#ff0000', stroke: '#0000ff', strokeWidth: 3, strokeDasharray: '' },
      containers: [{ id: 'C1', name: '容器1', enabled: true, nodes: ['N1'] }], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 容器 subgraph + style 行(在 styleLines)用面板配置色 (跳过按层级 LEVEL_STYLES)
    expect(result.mermaidCode).toContain('subgraph G_grp_color_c["彩色分组"]')
    expect(result.styleLines.some(l => l.includes('style G_grp_color_c fill:#ff0000,stroke:#0000ff,stroke-width:3'))).toBe(true)
  })

  it('[FIX 2026-08-19 自定义分组着色] 空分组上提节点用 group.style 色 (fill/stroke)', () => {
    const groups = [{
      id: 'grp_color_n', title: '彩色节点', groupType: 'custom', enabled: true,
      style: { fill: '#ff0000', stroke: '#0000ff' },
      containers: [], children: [], directNodes: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_grp_color_n')
    expect(result.mermaidCode).toContain('style COLLAPSE_grp_color_n fill:#ff0000,stroke:#0000ff')
  })

  it('[FIX 2026-08-19 自定义分组着色] ELK 系统分组(_elkGroup) 不受 group.style 着色影响', () => {
    const groups = [{
      id: 'G_elk', title: '有关系', groupType: 'custom', enabled: true, visible: false, _elkGroup: 'boundary',
      style: { fill: '#fff3e0', stroke: '#ff9800' },
      containers: [{ id: 'C1', name: '容器1', enabled: true, nodes: ['N1'] }], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // ELK 分组不应用 custom style 着色 (走原本无边框/系统逻辑), 不产生 G_elk 的颜色 style 行
    expect(result.styleLines.some(l => l.includes('style G_elk fill:#fff3e0,stroke:#ff9800'))).toBe(false)
  })

  it('container.collapsed=true -> 容器折叠为单个聚合节点, 节点外提不渲染', () => {
    const groups = [{
      id: 'G1', title: '组1', direction: 'LR',
      containers: [{ id: 'C1', name: '容器1', collapsed: true, nodes: ['N1'] }],
      children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_C')
    expect(result.mermaidCode).not.toContain('N1["节点1')
  })

  it('上提 submodule 分组标题追加祖先名称路径 (领域/子领域, 非编码)', () => {
    const upliftGroup = {
      id: 'G1', title: '需求计划 DP', enabled: true,
      info: { type: 'submodule', name: '需求计划', parent: '供应链计划', grandparent: '供应链云' },
      directNodes: [], containers: [], children: []
    }
    const result = generateGroupedLayout([upliftGroup], containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_G1')
    // 标题含祖先名称路径 (祖父/父), 且为名称而非编码, 用 \n 转义两行显示
    expect(result.mermaidCode).toContain('需求计划 DP')
    expect(result.mermaidCode).toContain('供应链云/供应链计划')
    expect(result.mermaidCode).toContain('\\n（供应链云/供应链计划）')
  })

  it('上提 module 分组标题追加父级名称路径 (领域)', () => {
    const upliftGroup = {
      id: 'G1', title: '供应链计划', enabled: true,
      info: { type: 'module', name: '供应链计划', parent: '供应链云' },
      directNodes: [], containers: [], children: []
    }
    const result = generateGroupedLayout([upliftGroup], containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('供应链云')
  })

  it('上提分组无祖先路径 (如 domain/自定义) 时标题不加路径', () => {
    const upliftGroup = {
      id: 'G1', title: '领域A', enabled: true,
      info: { type: 'domain', name: '领域A' },
      directNodes: [], containers: [], children: []
    }
    const result = generateGroupedLayout([upliftGroup], containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('COLLAPSE_G1')
    expect(result.mermaidCode).toContain('领域A')
    expect(result.mermaidCode).not.toContain('（')
  })

  it('[FIX 2026-08-06] info 缺失时上提服务模块标题从分组树推导祖先路径 (groupType=serviceModule)', () => {
    const groups = [{
      id: 'D_SCM', title: '供应链云', groupType: 'domain', enabled: true,
      children: [{
        id: 'SD_SCP', title: '供应链计划', groupType: 'subDomain', enabled: true,
        children: [{
          id: 'SM_DP', title: '需求计划', groupType: 'serviceModule', enabled: true,
          directNodes: [], containers: [], children: []
        }]
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 叶子服务模块无可见子孙 → 自动上提为聚合节点
    expect(result.mermaidCode).toContain('COLLAPSE_SM_DP')
    // info 缺失 (null) 时, 从祖先链 (供应链云/供应链计划) + groupType=serviceModule 推导路径
    expect(result.mermaidCode).toContain('需求计划\\n（供应链云/供应链计划）')
    // 祖先路径用名称而非编码
    expect(result.mermaidCode).not.toContain('SCM/SCP')
  })

  it('[FIX 2026-08-06] 上提叶子分组有 elementCode 时展示自身编码 而非祖先路径 (库存优化→SNPIO)', () => {
    const groups = [{
      id: 'D_SCM', title: '供应链云', groupType: 'domain', enabled: true,
      children: [{
        id: 'SD_SCP', title: '供应链计划', groupType: 'subDomain', enabled: true,
        children: [{
          id: 'SM_SNPIO', title: '库存优化', elementCode: 'SNPIO', groupType: 'serviceModule', enabled: true,
          directNodes: [], containers: [], children: []
        }]
      }]
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 叶子服务模块上提为聚合节点
    expect(result.mermaidCode).toContain('COLLAPSE_SM_SNPIO')
    // [TITLE 2026-08-09] 服务模块折叠节点: 名称置标记内, 类型+编码置下方 "[库存优化]\n服务模块 SNPIO"
    expect(result.mermaidCode).toContain('\\n服务模块 SNPIO')
    expect(result.mermaidCode).toContain('库存优化')
    // 不再展示祖先路径 (长路径会导致节点宽度溢出/遮挡, 且叶子元素应展示自身编码)
    expect(result.mermaidCode).not.toContain('供应链云/供应链计划')
  })

  it('[TITLE 2026-08-09] 折叠节点标题: 名称置标记内, 类型+编码置下方 (领域/子领域/服务模块)', () => {
    const cases = [
      { id: 'D_SCM', title: '供应链云', groupType: 'domain', elementCode: 'SCM', expect: '<供应链云>\\n领域 SCM' },
      { id: 'SD_SCP', title: '供应链计划', groupType: 'subDomain', elementCode: 'SCP', expect: '{供应链计划}\\n子领域 SCP' },
      { id: 'SM_SD', title: '销售', groupType: 'serviceModule', elementCode: 'SD', expect: '[销售]\\n服务模块 SD' }
    ]
    cases.forEach((c) => {
      const groups = [{
        id: c.id, title: c.title, groupType: c.groupType, elementCode: c.elementCode,
        directNodes: [], containers: [], children: []
      }]
      const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
      // 折叠节点应用 :::collapseNode (放大字体用)
      expect(result.mermaidCode).toContain(`COLLAPSE_${c.id.replace(/[^\w\u4e00-\u9fff]/g, '_')}`)
      expect(result.mermaidCode).toContain(':::collapseNode')
      // 标题 = "<名称>\n类型 编码"
      expect(result.mermaidCode).toContain(c.expect)
    })
  })

  it('[TITLE 2026-08-09] 折叠节点/容器标题剔除被拼入的父路径后缀 (销售(供应链云) → {销售})', () => {
    // 父分组名称泄漏到子分组标题的场景: group.title = "销售(供应链云)" (半角) / "销售（供应链云）" (全角)
    const cases = [
      { title: '销售(供应链云)', expect: '{销售}\\n子领域 SD' },
      { title: '销售（供应链云）', expect: '{销售}\\n子领域 SD' }
    ]
    cases.forEach((c) => {
      const groups = [{
        id: 'SD_SD', title: c.title, groupType: 'subDomain', elementCode: 'SD',
        directNodes: [], containers: [], children: []
      }]
      const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
      // 折叠节点标记内仅显示自身名称, 不含父路径
      expect(result.mermaidCode).toContain(c.expect)
      expect(result.mermaidCode).not.toContain('供应链云')
      // 容器标题 (subgraph) 同样剔除父路径
      expect(result.mermaidCode).toContain('{销售}')
    })
  })
})

// [ELK-GROUP 2026-08-12] 系统自动分组 (无关系/有关系, _elkGroup=inner/boundary).
//   [ELK-SEM 2026-08-14] 语义对齐 (用户确认): enabled=true 的 ELK 分组**始终创建 subgraph
//   容器**, visible=false 仅表示"容器在但无边框/无标题" (隐藏不影响容器渲染), 不再复用
//   disabled 打平分支 (原实现删容器 → 与禁用视觉一致 → "隐藏态污染启用" bug).
//   打平分支仅用于 enabled=false (禁用: 无容器). 两种分支渲染 ELK 节点时都**按分组**
//   收集节点 id → 链式虚拟边 (buildLayoutHelperEdges), 防 ELK 无连线节点单行平铺.
describe('groupedLayout - ELK 系统自动分组 (无关系/有关系)', () => {
  it('enabled=true + visible=false → 无边框 subgraph (容器在): subgraph G_id[ ], 透明样式, 节点在容器内', () => {
    const groups = [{
      id: 'G1', title: '无关系', _elkGroup: 'inner', enabled: true, visible: false,
      directNodes: ['N1', 'N2'], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // [ELK-SEM 2026-08-14] 隐藏 ≠ 打平: 容器必须存在 (enabled=true 必有容器), 无标题
    expect(result.mermaidCode).toContain('subgraph G_G1[ ]')
    // 节点在容器内渲染, 不消失
    expect(result.mermaidCode).toContain('N1')
    expect(result.mermaidCode).toContain('N2')
    // 无边框容器: 透明样式 (容器在但不可见, 样式行在 styleLines)
    expect(result.styleLines.join('\n')).toContain('style G_G1 fill:none,stroke:none')
    // 节点被收集 → 生成布局辅助虚拟边 (收集顺序跟随渲染顺序 reversedNodes: N2→N1)
    expect(result.layoutHelperEdges).toEqual([{ source: 'N2', target: 'N1' }])
  })

  it('enabled=true + visible=true → 有标题 subgraph + 收集虚拟边', () => {
    const groups = [{
      id: 'G1', title: '无关系', _elkGroup: 'inner', enabled: true, visible: true,
      directNodes: ['N1', 'N2'], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1["无关系"]')
    expect(result.mermaidCode).toContain('N1')
    // [ELK-SEM 2026-08-14] 有边框同样收集 (透明边仅增强约束, 防单行), 不再返回空
    expect(result.layoutHelperEdges).toEqual([{ source: 'N2', target: 'N1' }])
  })

  it('enabled=false → 打平: 无 subgraph, 节点直接渲染到父层', () => {
    const groups = [{
      id: 'G1', title: '有关系', _elkGroup: 'boundary', enabled: false, visible: false,
      directNodes: ['N1', 'N2'], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).not.toMatch(/subgraph G_G1/)
    expect(result.mermaidCode).toContain('N1')
    expect(result.mermaidCode).toContain('N2')
    // disabled 分支同样打平 → 收集节点 → 有虚拟边
    expect(result.layoutHelperEdges.length).toBe(1)
  })
})

// [ELK-FLAT 2026-08-14] 布局辅助虚拟边: 把打平 ELK 分组的孤立节点引导成多列网格.
//   纯函数 buildLayoutHelperEdges 直接单测 + 集成行为 (打平收集 → 返回值) 双覆盖.
describe('groupedLayout - ELK-FLAT 布局辅助虚拟边', () => {
  it('节点 < 2 → 无边', () => {
    expect(buildLayoutHelperEdges([])).toEqual([])
    expect(buildLayoutHelperEdges(['A'])).toEqual([])
    expect(buildLayoutHelperEdges(null)).toEqual([])
  })

  it('节点 ≤ 12 → 单链, 按顺序两两相连 (n-1 条边)', () => {
    const edges = buildLayoutHelperEdges(['N1', 'N2', 'N3', 'N4'])
    expect(edges).toEqual([
      { source: 'N1', target: 'N2' },
      { source: 'N2', target: 'N3' },
      { source: 'N3', target: 'N4' },
    ])
  })

  it('58 节点 → 按 12 切片成 5 链 (12/12/12/12/10), 共 53 条边', () => {
    const ids = Array.from({ length: 58 }, (_, i) => `N${i + 1}`)
    const edges = buildLayoutHelperEdges(ids)
    expect(edges.length).toBe(53) // 4 条满链 × 11 + 末链 9
    // 链内两两相连
    expect(edges.some(e => e.source === 'N1' && e.target === 'N2')).toBe(true)
    expect(edges.some(e => e.source === 'N11' && e.target === 'N12')).toBe(true)
    expect(edges.some(e => e.source === 'N13' && e.target === 'N14')).toBe(true)
    expect(edges.some(e => e.source === 'N57' && e.target === 'N58')).toBe(true)
    // 链边界不跨链相连 (N12 是链1末尾, N13 是链2开头)
    expect(edges.some(e => e.source === 'N12' && e.target === 'N13')).toBe(false)
    // 前 12 节点仅内部相连, 无跨链边
    expect(edges.every(e => !(e.source === 'N1' && e.target !== 'N2'))).toBe(true)
  })

  it('集成: ELK 分组 visible=false → 无边框 subgraph + directNodes 节点被收集并生成链式边', () => {
    const groups = [{
      id: 'G1', title: '无关系', _elkGroup: 'inner', enabled: true, visible: false,
      directNodes: ['N1', 'N2', 'N3'], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // [ELK-SEM 2026-08-14] 容器在 (无标题 subgraph), 不再是打平
    expect(result.mermaidCode).toContain('subgraph G_G1[ ]')
    // 收集顺序跟随渲染顺序 (reversedNodes: N3→N2→N1)
    expect(result.layoutHelperEdges).toEqual([
      { source: 'N3', target: 'N2' },
      { source: 'N2', target: 'N1' },
    ])
  })

  it('集成: 多个 ELK 分组按组收集 → 虚拟边不跨组连接', () => {
    const groups = [
      { id: 'G1', title: '无关系', _elkGroup: 'inner', enabled: true, visible: false,
        directNodes: ['N1', 'N2'], children: [] },
      { id: 'G2', title: '有关系', _elkGroup: 'boundary', enabled: true, visible: false,
        directNodes: ['N3'], children: [] }
    ]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    // 两组分别收集: 组1 [N2,N1] → 1 边; 组2 [N3] 单节点 → 无边. 无跨组边 (N1↔N3 / N2↔N3)
    expect(result.layoutHelperEdges).toEqual([{ source: 'N2', target: 'N1' }])
  })

  it('集成: _isDirectNodesContainer 容器内的节点同样被收集', () => {
    const groups = [{
      id: 'G1', title: '有关系', _elkGroup: 'boundary', enabled: true, visible: false,
      directNodes: [], containers: [{ _isDirectNodesContainer: true, nodes: ['N1', 'N2'] }], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).toContain('subgraph G_G1[ ]')
    expect(result.layoutHelperEdges).toEqual([{ source: 'N1', target: 'N2' }])
  })

  it('普通分组 enabled=false 打平 → 不收集节点 (layoutHelperEdges 为空)', () => {
    const groups = [{
      id: 'G1', title: '禁用组', enabled: false, visible: true,
      directNodes: ['N1', 'N2'], children: []
    }]
    const result = generateGroupedLayout(groups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result.mermaidCode).not.toMatch(/subgraph G_G1/)
    expect(result.layoutHelperEdges).toEqual([])
  })

  it('跨调用不残留: 上次打平收集的节点不影响本次调用', () => {
    const flatGroups = [{
      id: 'G1', title: '内', _elkGroup: 'inner', enabled: true, visible: false,
      directNodes: ['N1', 'N2'], children: []
    }]
    const normalGroups = [{
      id: 'G2', title: '普通组', containers: [containers[0]], children: []
    }]
    generateGroupedLayout(flatGroups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    const result2 = generateGroupedLayout(normalGroups, containers, makeNodeMap(nodes), makeDefinedNodes(), 'TB')
    expect(result2.layoutHelperEdges).toEqual([])
  })
})
