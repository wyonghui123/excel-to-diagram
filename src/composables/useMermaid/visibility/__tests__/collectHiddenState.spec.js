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

  it('ELK 系统分组自身可见性为 false 不判为有内容', () => {
    expect(hasVisibleContent(invElkChildren[0])).toBe(false)
  })
})

describe('collectHiddenState - ELK 系统分组回归 (THE bug)', () => {
  it('隐藏项目云: 采购供应(BO 在 ELK 系统分组下)不得被收集为隐藏', () => {
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

    // 项目云自身应被收集
    expect(hiddenContainerCodes.has('PM')).toBe(true)
    expect(hiddenContainerCodes.has('PROJ')).toBe(true)
    expect(hiddenNodeCodes.has('PMCCP015')).toBe(true)   // 经 PM 的 ELK 分组收集 (隐藏真实分组时应收)
    expect(hiddenNodeCodes.has('PMCCP016')).toBe(true)
  })

  it('隐藏采购供应自身: 其 BO (经 ELK 分组) 应被收集', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].children[0].visible = false   // 隐藏 MM
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: noProtect })
    for (const code of ['INV01', 'INV02', 'INV03', 'PR01', 'PR02']) {
      expect(hiddenNodeCodes.has(code), `${code} 应被隐藏`).toBe(true)
    }
    expect(hiddenContainerCodes.has('MM')).toBe(true)
  })
})

describe('collectHiddenState - 对象范围保护', () => {
  it('隐藏范围祖先的真实树结果: 非范围子孙隐藏, 范围链 (MM/INV) 保持', () => {
    const cfg = JSON.parse(JSON.stringify(groups))
    // 模拟"隐藏供应链云"经 setVis 后的真实树: SCM.visible=true(祖先保护),
    // MM.visible=true(直接保护), 其他非范围子领域 SCP.visible=false
    cfg[0].children.push({
      id: 'G_SD_SCP', elementCode: 'SCP', groupType: 'subDomain', visible: false,
      directNodes: ['SCP01'],
    })
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenNodeCodes, hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })

    expect(hiddenContainerCodes.has('SCP')).toBe(true)   // 非范围子孙隐藏
    expect(hiddenNodeCodes.has('SCP01')).toBe(true)
    expect(hiddenContainerCodes.has('MM')).toBe(false)   // 直接范围分组保持
    expect(hiddenNodeCodes.has('INV01')).toBe(false)     // 范围内 BO 保持
  })

  it('范围祖先自身不因隐藏操作被收集 (visible 由 setVis 保持 true, 防御兜底)', () => {
    // setVis 不会把范围祖先设为 false; 若异常出现, isScopeProtected 兜底不收集
    const cfg = JSON.parse(JSON.stringify(groups))
    cfg[0].visible = false   // 异常态: 范围祖先 visible=false
    const protect = (g) => g.elementCode === 'MM' || g.elementCode === 'SCM' || g.elementCode === 'G_SD_MM'
    const { hiddenContainerCodes } = collectHiddenState(cfg, { isScopeProtected: protect })
    expect(hiddenContainerCodes.has('SCM')).toBe(false)   // 范围祖先受保护
    expect(hiddenContainerCodes.has('MM')).toBe(false)
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
