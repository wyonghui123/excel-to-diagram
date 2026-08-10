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
import { generateGroupedLayout, getLiftedParentPathMap } from '../groupedLayout'
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
