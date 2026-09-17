/**
 * collectHiddenState.spec.js - 增量隐藏集合计算
 * 回归保护:
 *  - 2026-08-14 ELK 系统分组误判为用户隐藏 bug
 *    (隐藏任意分组 → ELK 系统分组(无关系/有关系, _elkGroup=inner/boundary) 的
 *     visible=false 被当作"用户隐藏" → 其下 BO 全被收集为隐藏 → display:none 且无法恢复)
 *  - 2026-09-03 子领域/服务模块容器同时含 nodes=BO 编码 + children=子节点, 旧递归
 *    只读 g.directNodes/g.containers/g.children, 漏收集该层 nodes 数组里的 BO 编码,
 *    父分组隐藏后 BO 节点仍可见.
 */
import { describe, it, expect } from 'vitest'
import { collectHiddenState, hasVisibleContent, isElkSystemAuto } from '../collectHiddenState.js'

// 模拟采购供应(MM)下 ELK 服务模块: INV 的 BO 被"无关系/有关系"系统分组包裹
const invElkChildren = [
  { id: 'G_ELK_INV_inner', elementCode: 'INV_inner', groupType: 'custom', _elkGroup: 'inner', visible: false, directNodes: ['INV01', 'INV02'] },
  { id: 'G_ELK_INV_boundary', elementCode: 'INV_boundary', groupType: 'custom', _elkGroup: 'boundary', visible: false, directNodes: ['INV03'] },
]

const groups = [
  {
    id: 'D_SCM', elementCode: 'SCM', title: '供应链云', groupType: 'domain', visible: true,
    children: [
      {
        id: 'G_SD_MM', elementCode: 'MM', title: '采购供应', groupType: 'subDomain', visible: true,
        children: [
          {
            id: 'G_SM_INV', elementCode: 'INV', title: '库存', groupType: 'serviceModule', visible: true,
            children: invElkChildren,
          },
          {
            id: 'G_SM_PR', elementCode: 'PR', title: '采购请求', groupType: 'serviceModule', visible: true,
            directNodes: ['PR01', 'PR02'],
          },
        ],
      },
    ],
  },
  {
    id: 'D_PM', elementCode: 'PM', title: '项目云', groupType: 'domain', visible: true,
    children: [
      {
        id: 'G_SD_PROJ', elementCode: 'PROJ', title: '项目管理', groupType: 'subDomain', visible: true,
        children: [
          {
            id: 'G_SM_PMCCP', elementCode: 'PMCCP', title: '项目合同履约', groupType: 'serviceModule', visible: true,
            children: [
              { id: 'G_ELK_PM_inner', elementCode: 'PM_inner', groupType: 'custom', _elkGroup: 'inner', visible: false, directNodes: ['PMCCP015'] },
              { id: 'G_ELK_PM_boundary', elementCode: 'PM_boundary', groupType: 'custom', _elkGroup: 'boundary', visible: false, directNodes: ['PMCCP016'] },
            ],
          },
        ],
      },
    ],
  },
]

const noProtect = () => false

describe('isElkSystemAuto / hasVisibleContent', () => {
  it('识别 ELK 系统分组', () => {
    expect(isElkSystemAuto(invElkChildren[0])).toBe(true)   // inner
    expect(isElkSystemAuto(invElkChildren[1])).toBe(true)   // boundary
    expect(isElkSystemAuto({ groupType: 'custom', _elkGroup: 'inner' })).toBe(true)
    expect(isElkSystemAuto({ _elkGroup: 'custom' })).toBe(false)
    expect(isElkSystemAuto(null)).toBe(false)
  })

  it('仅含 ELK 系统分组子级的服务模块不判为空容器 (有内容)', () => {
    const inv = groups[0].children[0].children[0]
    expect(hasVisibleContent(inv)).toBe(true)   // 回归: 之前误判 false → INV 被隐藏
  })

  it('ELK 系统分组自身可见性为 false 仍有节点 → 视为有内容', () => {
    // [HIDE 2026-08-19] 隐藏仅作用于容器框, 分组仍有 directNodes 渲染 → 非空容器
    expect(hasVisibleContent(invElkChildren[0])).toBe(true)
  })
})

describe('collectHiddenState - ELK 系统分组回归 (THE bug)', () => {
  it('[回归 2026-08-14] ELK 系统分组自身的 visible=false 不被当作用户隐藏 → 其 BO 不收集', () => {
    // 所有真实分组可见, 仅 ELK 系统分组 (inner/boundary) visible=false ("无边框盒"语义)
    const cfg = JSON.parse(JSON.stringify(groups))
    const { hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    for (const code of ['INV01', 'INV02', 'INV03']) {
      expect(hiddenNodeCodes.has(code), `${code} 不应被收集为隐藏`).toBe(false)
    }
  })

  it('[HIDE 2026-08-22][FIX BUG-V033 2026-09-03] 隐藏项目云: 各级容器框 + 子孙 BO 全隐藏, 其他子树不受影响', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[1].visible = false   // 隐藏 PM
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })

    // 采购供应 (SCM 子树) BO 必须保持可见 (与 PM 无关)
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 不应被隐藏`).toBe(false)
    }
    // 采购供应容器不应被隐藏 (含空容器判定: INV 不判空)
    for (const c of ['INV', 'G_SM_INV', 'MM', 'G_SD_MM', 'SCM', 'D_SCM']) {
      expect(hiddenContainerCodes.has(c), `容器 ${c} 不应被隐藏`).toBe(false)
    }

    // [HIDE 2026-08-22] PM 容器框 + 其下 PMCCP 的 BO 一并隐藏
    expect(hiddenContainerCodes.has('PM')).toBe(true)
    // [FIX BUG-V033 2026-09-03] 中间容器 PROJ 也级联隐藏 (新语义: 子容器框一起)
    expect(hiddenContainerCodes.has('PROJ')).toBe(true)
    expect(hiddenContainerCodes.has('PMCCP')).toBe(true)
    expect(hiddenNodeCodes.has('PMCCP015')).toBe(true)     // 末端节点整体隐藏
    expect(hiddenNodeCodes.has('PMCCP016')).toBe(true)
  })

  it('[HIDE 2026-08-22] 隐藏采购供应: 容器框 + 其下 BO 整体隐藏 (含 ELK 分组内的 BO)', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].children[0].visible = false   // 隐藏 MM
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    // 采购供应容器框隐藏
    expect(hiddenContainerCodes.has('MM')).toBe(true)
    // 其下 BO 全部隐藏 (含 ELK 系统分组 inner/boundary 内的 BO)
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 应被隐藏`).toBe(true)
    }
  })
})

describe('collectHiddenState - 隐藏与对象范围保护 [HIDE 2026-08-22]', () => {
  it('[HIDE 2026-08-22] 隐藏 SCP: 容器框 + 其下 BO 整体隐藏 (BO 非范围内)', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].children.push({
      id: 'G_SD_SCP', elementCode: 'SCP', groupType: 'subDomain', visible: false,
      directNodes: ['SCP01'],
    })
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })

    expect(hiddenContainerCodes.has('SCP')).toBe(true)   // SCP 容器框隐藏
    expect(hiddenNodeCodes.has('SCP01')).toBe(true)      // [HIDE 2026-08-22] 其下 BO 一并隐藏
    expect(hiddenContainerCodes.has('MM')).toBe(false)   // 未隐藏的分组不受影响
    expect(hiddenNodeCodes.has('INV01')).toBe(false)     // 其他子树 BO 保留
  })

  it('[HIDE 2026-08-22] 隐藏 SCM: 容器框隐藏, 但范围内 MM 子树 (及祖先) 的 BO 保留', () => {
    // 隐藏范围祖先 SCM, 范围内服务模块 MM 的 BO 受保护不隐藏 (仅容器框隐藏)
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].visible = false   // 隐藏 SCM
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })
    expect(hiddenContainerCodes.has('SCM')).toBe(true)   // 容器框可隐藏
    // 范围内 MM 子树整棵跳过收集 → 其 BO 全部保留
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 应受范围保护保留`).toBe(false)
    }
  })
})

describe('collectHiddenState - 空容器隐藏', () => {
  it('可见但整棵子树无内容的分组 → 隐藏其容器', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    // 制造空容器: 把 INV/PR 的 BO 移走
    cfg[0].children[0].children[0].children = []
    cfg[0].children[0].children[0].directNodes = []
    cfg[0].children[0].children[1].directNodes = []
    const { hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('INV')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(true)
  })
})

describe('collectHiddenState - BO 虚拟叶容器 (nodes 数组) 隐藏 [FIX 2026-08-19]', () => {
  // BO 叶在面板树中表示为 isVirtual=true 的容器, nodes=[业务编码]
  const boLeafCfg = [
    {
      id: 'D_SCM', elementCode: 'SCM', title: '供应链云', groupType: 'domain', visible: true,
      children: [
        {
          id: 'G_SD_SCP', elementCode: 'SCP', title: '供应链计划', groupType: 'subDomain', visible: true,
          children: [
            {
              id: 'G_SM_DP', elementCode: 'DP', title: '需求计划', groupType: 'serviceModule', visible: true,
              containers: [
                { id: 'VC_DP10', isVirtual: true, nodes: ['DP10'] },
                { id: 'VC_DP01', isVirtual: true, nodes: ['DP01'] },
              ],
            },
          ],
        },
      ],
    },
  ]

  it('单个 BO 叶容器 visible=false → 其 nodes 编码被收集为隐藏节点', () => {
    const cfg = JSON.parse(JSON.stringify(boLeafCfg))
    cfg[0].children[0].children[0].containers[0].visible = false   // 隐藏 DP10
    const { hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenNodeCodes.has('DP10')).toBe(true)    // 回归: 之前 nodes 未被收集 → DP10 不隐藏
    expect(hiddenNodeCodes.has('DP01')).toBe(false)   // 未隐藏的 BO 保持可见
  })

  it('分组隐藏: BO 虚拟叶容器内的节点被级联收集隐藏 [HIDE 2026-08-22]', () => {
    const cfg = JSON.parse(JSON.stringify(boLeafCfg))
    cfg[0].children[0].visible = false   // 隐藏 SCP → 容器框 + 其下 BO 一并隐藏
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('SCP')).toBe(true)   // SCP 容器框隐藏
    expect(hiddenNodeCodes.has('DP10')).toBe(true)       // [HIDE 2026-08-22] 叶容器 nodes 被级联收集
    expect(hiddenNodeCodes.has('DP01')).toBe(true)
  })
})

describe('collectHiddenState - 子领域/服务模块自身的 nodes 字段级联 [FIX 2026-09-03]', () => {
  // [HIDE 2026-09-03] 背景: 子领域/服务模块容器同时含 nodes=[BO 编码] 和 children=子节点.
  //   旧实现 collectDescendantNodeCodes 只读 g.directNodes + 递归 g.containers/g.children,
  //   漏掉 g.nodes 字段 → 父分组(领域 D_PROC)隐藏后, 子领域(供应商管理)节点里的 BO 编码 (PUM01 等)
  //   不在 hiddenNodeCodes, SVG 仍显示. 修复: 在递归入口增加 g.nodes 收集.
  const procWithMixedNodes = [
    {
      id: 'D_PROC', elementCode: 'PROC', title: '采购云', groupType: 'domain', visible: false,
      children: [
        {
          id: 'G_SD_SMT', elementCode: 'SMT', title: '供应商管理', groupType: 'subDomain', visible: true,
          // 关键: subDomain 同时含 nodes (BO 编码数组) + children (子节点)
          nodes: ['PUM01', 'PUM02'],
          children: [
            {
              id: 'G_SM_PR', elementCode: 'PR', title: '采购请求', groupType: 'serviceModule', visible: true,
              directNodes: ['PR01'],
            },
          ],
        },
      ],
    },
  ]

  it('隐藏 PROC: subDomain 自身的 nodes (PUM01/PUM02) 必须级联收集隐藏', () => {
    const cfg = JSON.parse(JSON.stringify(procWithMixedNodes))
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    // PROC 容器框 + 子孙 BO 整体隐藏
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    // 回归保护 [FIX 2026-09-03]: subDomain.nodes 里的 PUM01/PUM02 之前漏收集
    expect(hiddenNodeCodes.has('PUM01')).toBe(true)
    expect(hiddenNodeCodes.has('PUM02')).toBe(true)
    // 子孙 directNodes 也要收集
    expect(hiddenNodeCodes.has('PR01')).toBe(true)
  })

  it('隐藏 SMT: 自身的 nodes + children.directNodes 全部级联隐藏', () => {
    const cfg = JSON.parse(JSON.stringify(procWithMixedNodes))
    cfg[0].visible = true   // PROC 保持可见
    cfg[0].children[0].visible = false   // 隐藏 SMT
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('PROC')).toBe(false)   // 父级保持可见
    expect(hiddenContainerCodes.has('SMT')).toBe(true)     // SMT 容器框隐藏
    expect(hiddenNodeCodes.has('PUM01')).toBe(true)        // 自身 nodes
    expect(hiddenNodeCodes.has('PUM02')).toBe(true)
    expect(hiddenNodeCodes.has('PR01')).toBe(true)         // 子孙 directNodes
  })

  it('nodes 字段为对象数组 [{code}] 也应正确收集', () => {
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: false,
        children: [
          { id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: true,
            nodes: [{ code: 'PUM01' }, { code: 'PUM02' }] },
        ],
      },
    ]
    const { hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenNodeCodes.has('PUM01')).toBe(true)
    expect(hiddenNodeCodes.has('PUM02')).toBe(true)
  })
})

describe('collectHiddenState - 父分组隐藏后子容器框级联隐藏 [FIX BUG-V033 2026-09-03]', () => {
  // 根因: 用户反馈"隐藏采购云后子分组容器仍可见". 旧实现 collectDescendantNodeCodes 只把
  //   子孙 BO 编码加入 hiddenNodeCodes, 未把子分组自身的 code 加入 hiddenContainerCodes,
  //   导致 MermaidComponent.updateVisibilityOnly 中 g.cluster 的 display 仍为 ''.
  // 修复: collectDescendantNodeCodes 增加第 4 参数 hiddenContainerCodes, 递归时同步收集
  //   子分组的 elementCode/id 到 hiddenContainerCodes.

  const procTree = [
    {
      id: 'D_PROC', elementCode: 'PROC', title: '采购云', groupType: 'domain', visible: false,
      children: [
        {
          id: 'G_SD_SMT', elementCode: 'SMT', title: '供应商管理', groupType: 'subDomain', visible: true,
          nodes: ['PUM01', 'PUM02'],
          children: [
            {
              id: 'G_SM_PR', elementCode: 'PR', title: '采购请求', groupType: 'serviceModule', visible: true,
              directNodes: ['PR01'],
            },
          ],
        },
      ],
    },
  ]

  it('隐藏 PROC: 子领域 SMT 和服务模块 PR 的容器框必须级联进 hiddenContainerCodes', () => {
    const cfg = JSON.parse(JSON.stringify(procTree))
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    // PROC 自身 (主动隐藏)
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    // [FIX BUG-V033 2026-09-03] 回归保护: 子分组容器框级联隐藏
    expect(hiddenContainerCodes.has('SMT')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(true)
    // BO 编码仍正确收集到 hiddenNodeCodes
    expect(hiddenNodeCodes.has('PUM01')).toBe(true)
    expect(hiddenNodeCodes.has('PUM02')).toBe(true)
    expect(hiddenNodeCodes.has('PR01')).toBe(true)
  })

  it('隐藏 PROC 的子树 (ELK 容器包裹): 各级容器框 + ELK 子级 BO 全级联隐藏', () => {
    const cfg = JSON.parse(JSON.stringify(procTree))
    cfg[0].children[0].children[0].children = [
      { id: 'G_ELK_PR_inner', elementCode: 'PR_inner', groupType: 'custom', _elkGroup: 'inner', visible: false, directNodes: ['PR02'] },
      { id: 'G_ELK_PR_boundary', elementCode: 'PR_boundary', groupType: 'custom', _elkGroup: 'boundary', visible: false, directNodes: ['PR03'] },
    ]
    cfg[0].children[0].children[0].directNodes = []
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    expect(hiddenContainerCodes.has('SMT')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(true)
    // ELK 子级自身不是用户隐藏, 不进 hiddenContainerCodes
    expect(hiddenContainerCodes.has('PR_inner')).toBe(false)
    expect(hiddenContainerCodes.has('PR_boundary')).toBe(false)
    // ELK 子级 BO 仍级联隐藏 (旧语义保持)
    expect(hiddenNodeCodes.has('PR02')).toBe(true)
    expect(hiddenNodeCodes.has('PR03')).toBe(true)
  })

  it('对象范围保护: 隐藏 PROC, 但范围内 SMT 子树受保护 → SMT/PR 容器框与 BO 均保留', () => {
    const cfg = JSON.parse(JSON.stringify(procTree))
    // 范围保护命中 SMT/PR 子树整棵
    const protect = (g) => ['SMT', 'PR', 'G_SD_SMT', 'G_SM_PR'].includes(g.elementCode) || ['G_SD_SMT', 'G_SM_PR'].includes(g.id)
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })
    // PROC 自身 (祖先, 但 isScopeProtected 不返回 true 因为其 elementCode 是 PROC 而非 SMT)
    // 注: 当前 protect 只保护 SMT/PR, PROC 不在范围内, PROC 容器框被收集
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    // [FIX BUG-V033] 保护命中的子树不再级联
    expect(hiddenContainerCodes.has('SMT')).toBe(false)
    expect(hiddenContainerCodes.has('PR')).toBe(false)
    expect(hiddenNodeCodes.has('PUM01')).toBe(false)
    expect(hiddenNodeCodes.has('PR01')).toBe(false)
  })

  it('中间层 (subDomain) 隐藏: 其自身 + 服务模块 (子) 容器框级联隐藏, 父领域保留', () => {
    const cfg = JSON.parse(JSON.stringify(procTree))
    cfg[0].visible = true   // PROC 保持可见
    cfg[0].children[0].visible = false   // 隐藏 SMT
    const { hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('PROC')).toBe(false)
    expect(hiddenContainerCodes.has('SMT')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(true)
  })

  it('BO 虚拟叶容器隐藏: 子级 BO 虚拟叶容器的容器框也级联隐藏', () => {
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: false,
        children: [
          {
            id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: true,
            children: [
              {
                id: 'G_SM_PR', elementCode: 'PR', groupType: 'serviceModule', visible: true,
                containers: [
                  { id: 'VC_PR10', isVirtual: true, nodes: ['PR10'] },
                  { id: 'VC_PR11', isVirtual: true, nodes: ['PR11'] },
                ],
              },
            ],
          },
        ],
      },
    ]
    const { hiddenContainerCodes, hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    expect(hiddenContainerCodes.has('SMT')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(true)
    // BO 虚拟叶容器也是 g.cluster, code 是其 id (VC_PR10) → 容器框隐藏
    expect(hiddenContainerCodes.has('VC_PR10')).toBe(true)
    expect(hiddenContainerCodes.has('VC_PR11')).toBe(true)
    expect(hiddenNodeCodes.has('PR10')).toBe(true)
    expect(hiddenNodeCodes.has('PR11')).toBe(true)
  })
})

describe('collectHiddenState - 展开层级下的上提节点隐藏 [FIX BUG-V034 2026-09-03]', () => {
  // 根因: 用户反馈"展开到子领域/服务模块后再隐藏父分组, 子节点仍可见".
  //   展开到子领域时, 子领域被上提为 COLLAPSE_<id> 聚合节点 (group._uplift=true,
  //   见 upliftDerivation.js), 渲染为 g.node 而非 g.cluster.
  //   旧实现 collectDescendantNodeCodes 一律 add 子分组 code 到 hiddenContainerCodes
  //   (即使它渲染成 g.node, 进 hiddenContainerCodes 是无效的). 同时上提节点的 id 应进
  //   hiddenCollapseIds (MermaidComponent:1713-1718 svg.querySelectorAll('g.node[id^=
  //   flowchart-COLLAPSE_"]').forEach) 才能从 SVG 消失.
  // 修复: collectDescendantNodeCodes 增加第 5 参数 hiddenCollapseIds; children 分支判
  //   ch._uplift: 上提节点 add COLLAPSE_<id> 到 hiddenCollapseIds, 跳过 hiddenContainerCodes.

  const noProtect = () => false

  it('展开到子领域: SMT 被上提 (_uplift=true), 隐藏 PROC → SMT 上提节点 id 进 hiddenCollapseIds', () => {
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', title: '采购云', groupType: 'domain', visible: false,
        children: [
          {
            id: 'G_SD_SMT', elementCode: 'SMT', title: '供应商管理', groupType: 'subDomain',
            visible: true, _uplift: true,
            children: [
              { id: 'G_SM_PR', elementCode: 'PR', groupType: 'serviceModule', visible: true,
                directNodes: ['PR01'] },
            ],
          },
        ],
      },
    ]
    const { hiddenCollapseIds, hiddenContainerCodes, hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    // PROC 隐藏: PROC 自身上提 id 进入 hiddenCollapseIds (保留旧语义)
    expect(hiddenCollapseIds.has('COLLAPSE_D_PROC')).toBe(true)
    // [FIX BUG-V034 2026-09-03] 回归保护: SMT 上提节点 id 应进入 hiddenCollapseIds
    expect(hiddenCollapseIds.has('COLLAPSE_G_SD_SMT')).toBe(true)
    // [FIX BUG-V034 2026-09-03] 回归保护: SMT 不应进 hiddenContainerCodes (它渲染成 g.node)
    expect(hiddenContainerCodes.has('SMT')).toBe(false)
    // PROC 容器框 (PROC 自己没上提) 仍正确收集
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
    // PR (serviceModule, 没上提) 容器框级联收集
    expect(hiddenContainerCodes.has('PR')).toBe(true)
    // 末端 BO 仍正确
    expect(hiddenNodeCodes.has('PR01')).toBe(true)
  })

  it('展开到服务模块: PR 被上提 (_uplift=true), 隐藏 PROC → PR 上提节点 id 进 hiddenCollapseIds', () => {
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: false,
        children: [
          {
            id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: true,
            children: [
              {
                id: 'G_SM_PR', elementCode: 'PR', groupType: 'serviceModule', visible: true,
                _uplift: true,
                directNodes: ['PR01'],
              },
            ],
          },
        ],
      },
    ]
    const { hiddenCollapseIds, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenCollapseIds.has('COLLAPSE_G_SM_PR')).toBe(true)
    expect(hiddenContainerCodes.has('PR')).toBe(false)
    // SMT, PROC 容器框级联收集
    expect(hiddenContainerCodes.has('SMT')).toBe(true)
    expect(hiddenContainerCodes.has('PROC')).toBe(true)
  })

  it('用户主动隐藏一个已被上提的分组: visible=false + _uplift=true, 只进 hiddenCollapseIds', () => {
    // 例如 legend 点击"供应商管理" (已被上提为聚合节点), 它只渲染为 g.node
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: true,
        // 故意加一个 directNodes, 防止 PROC 被"空容器隐藏"收集规则带进去 (聚焦测试 SMT)
        directNodes: ['PROC_BO'],
        children: [
          {
            id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: false, _uplift: true,
          },
        ],
      },
    ]
    const { hiddenCollapseIds, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenCollapseIds.has('COLLAPSE_G_SD_SMT')).toBe(true)
    // [FIX BUG-V034 2026-09-03] SMT 已上提, 没有 g.cluster, 不应进 hiddenContainerCodes
    expect(hiddenContainerCodes.has('SMT')).toBe(false)
    // PROC 自身有 directNodes, 不是空容器, 不应进 hiddenContainerCodes
    expect(hiddenContainerCodes.has('PROC')).toBe(false)
  })

  it('混合场景: 隐藏父 PROC, 部分子已上提 + 部分未上提, 各自走正确的隐藏路径', () => {
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: false,
        children: [
          // SMT 上提 → 走 hiddenCollapseIds
          { id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: true, _uplift: true },
          // SS (其他子领域) 未上提 → 走 hiddenContainerCodes
          { id: 'G_SD_SS', elementCode: 'SS', groupType: 'subDomain', visible: true,
            children: [
              { id: 'G_SM_SS1', elementCode: 'SS1', groupType: 'serviceModule', visible: true,
                _uplift: true, directNodes: ['SS101'] },
              { id: 'G_SM_SS2', elementCode: 'SS2', groupType: 'serviceModule', visible: true,
                directNodes: ['SS201'] },
            ],
          },
        ],
      },
    ]
    const { hiddenCollapseIds, hiddenContainerCodes, hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    // 上提节点走 hiddenCollapseIds
    expect(hiddenCollapseIds.has('COLLAPSE_G_SD_SMT')).toBe(true)
    expect(hiddenCollapseIds.has('COLLAPSE_G_SM_SS1')).toBe(true)
    // 未上提节点走 hiddenContainerCodes
    expect(hiddenContainerCodes.has('SS')).toBe(true)
    expect(hiddenContainerCodes.has('SS2')).toBe(true)
    // [FIX BUG-V034 2026-09-03] 上提节点的 code 不应混入 hiddenContainerCodes
    expect(hiddenContainerCodes.has('SMT')).toBe(false)
    expect(hiddenContainerCodes.has('SS1')).toBe(false)
    // 末端 BO 仍正确
    expect(hiddenNodeCodes.has('SS101')).toBe(true)
    expect(hiddenNodeCodes.has('SS201')).toBe(true)
  })

  it('ELK 系统分组子孙被上提的场景: 隐藏 PROC 时, 上提的 ELK 子孙不进 hiddenCollapseIds', () => {
    // 上提只对"用户可见的分组 (domain/subDomain/serviceModule/custom)" 生效,
    //   ELK 系统分组 (_elkGroup=inner/boundary) 不会被上提, 此测试仅证明 ELK 短路仍生效
    const cfg = [
      {
        id: 'D_PROC', elementCode: 'PROC', groupType: 'domain', visible: false,
        children: [
          {
            id: 'G_SD_SMT', elementCode: 'SMT', groupType: 'subDomain', visible: true,
            _uplift: true,
            children: [
              { id: 'G_ELK_inner', elementCode: 'SMT_inner', groupType: 'custom', _elkGroup: 'inner', visible: false,
                directNodes: ['BO_inner_1'] },
            ],
          },
        ],
      },
    ]
    const { hiddenCollapseIds, hiddenContainerCodes, hiddenNodeCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenCollapseIds.has('COLLAPSE_G_SD_SMT')).toBe(true)
    // ELK 子孙不应进 hiddenContainerCodes (旧保护)
    expect(hiddenContainerCodes.has('SMT_inner')).toBe(false)
    // ELK 子孙的 BO 仍正确收集 (旧行为)
    expect(hiddenNodeCodes.has('BO_inner_1')).toBe(true)
  })
})
