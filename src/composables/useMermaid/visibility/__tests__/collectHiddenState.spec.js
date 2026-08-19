/**
 * collectHiddenState.spec.js - 增量隐藏集合计算
 * 回归保护: 2026-08-14 ELK 系统分组误判为用户隐藏 bug
 *   (隐藏任意分组 → ELK 系统分组(无关系/有关系, _elkGroup=inner/boundary) 的
 *    visible=false 被当作"用户隐藏" → 其下 BO 全被收集为隐藏 → display:none 且无法恢复)
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
    expect(isElkSystemAuto({ _elkGroup: 'inner' })).toBe(true)
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
  it('隐藏项目云: 只隐藏其容器框, 子节点 (含 ELK 分组 BO) 保留', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[1].visible = false   // 隐藏 PM
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })

    // 采购供应 BO 必须保持可见 (核心回归断言)
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 不应被隐藏`).toBe(false)
    }
    // 采购供应容器不应被隐藏 (含空容器判定: INV 不判空)
    for (const c of ['INV', 'G_SM_INV', 'MM', 'G_SD_MM', 'SCM', 'D_SCM']) {
      expect(hiddenContainerCodes.has(c), `容器 ${c} 不应被隐藏`).toBe(false)
    }

    // [HIDE 2026-08-19] 新语义: 只隐藏 PM 容器框, 子容器/子节点保留
    expect(hiddenContainerCodes.has('PM')).toBe(true)
    expect(hiddenContainerCodes.has('PROJ')).toBe(false)   // 子容器保留
    expect(hiddenNodeCodes.has('PMCCP015')).toBe(false)    // 子节点保留
    expect(hiddenNodeCodes.has('PMCCP016')).toBe(false)
  })

  it('隐藏采购供应自身: 只隐藏容器框, BO 保留', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].children[0].visible = false   // 隐藏 MM
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 应保留可见`).toBe(false)
    }
    expect(hiddenContainerCodes.has('MM')).toBe(true)
  })
})

describe('collectHiddenState - 隐藏与对象范围保护 [HIDE 2026-08-19]', () => {
  it('隐藏分组只作用于容器框: SCP 容器框隐藏, 其 BO 保留', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].children.push({
      id: 'G_SD_SCP', elementCode: 'SCP', groupType: 'subDomain', visible: false,
      directNodes: ['SCP01'],
    })
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })

    expect(hiddenContainerCodes.has('SCP')).toBe(true)   // SCP 容器框隐藏
    expect(hiddenNodeCodes.has('SCP01')).toBe(false)     // 子节点保留 (新语义)
    expect(hiddenContainerCodes.has('MM')).toBe(false)   // 未隐藏的分组不受影响
    expect(hiddenNodeCodes.has('INV01')).toBe(false)     // BO 保留
  })

  it('范围内分组 (SCM) 容器框也可隐藏: 隐藏不再被范围保护阻断', () => {
    // 隐藏仅作用于容器框, 不隐藏任何范围内元素 (子节点保留), 故无需范围保护.
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].visible = false   // 隐藏 SCM (范围内祖先)
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })
    expect(hiddenContainerCodes.has('SCM')).toBe(true)   // 容器框可隐藏
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

  it('分组隐藏只隐藏容器框, BO 叶容器不被级联隐藏 [HIDE 2026-08-19]', () => {
    const cfg = JSON.parse(JSON.stringify(boLeafCfg))
    cfg[0].children[0].visible = false   // 隐藏 SCP → 只隐藏 SCP 容器框
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    expect(hiddenContainerCodes.has('SCP')).toBe(true)   // SCP 容器框隐藏
    expect(hiddenNodeCodes.has('DP10')).toBe(false)      // BO 保留 (新语义: 隐藏≠禁用)
    expect(hiddenNodeCodes.has('DP01')).toBe(false)
  })
})
