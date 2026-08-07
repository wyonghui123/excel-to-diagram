/**
 * linkRemapper 单测 (FR-003/004 回归保护, 2026-08-05 v2.1)
 *
 * 覆盖:
 * - 上提分组 (enabled 且无可见子孙) → 全部后代节点编码重映射到聚合节点
 * - 最近上提祖先优先 (父非上提, 子上提)
 * - 两端上提到同一聚合节点 → 丢弃 (自环)
 * - 无上提时原样返回
 * - 保留原始关系元数据
 * - upliftNodeId 编码稳定且与 groupedLayout 一致
 */
import { describe, it, expect } from 'vitest'
import { buildUpliftAncestorMap, remapLinksToVisibleAncestors, fuseLinks } from '../linkRemapper'
import { upliftNodeId } from '../upliftDerivation'

// "仅服务模块"场景: 领域A 为容器, 其下 服务模块PM1 内部 BO 全禁用 → PM1 上提为聚合节点
const onlySM = [
  {
    id: 'D1', title: '领域A', elementCode: 'DA', groupType: 'domain', enabled: true, directNodes: ['BO_ROOT'],
    children: [
      {
        id: 'SM1', title: '服务模块PM1', elementCode: 'PM1', groupType: 'serviceModule', enabled: true,
        containers: [
          { id: 'bo1', elementCode: 'BO1', isVirtual: true, enabled: false, nodes: ['BO1'] },
          { id: 'bo2', elementCode: 'BO2', isVirtual: true, enabled: false, nodes: ['BO2'] }
        ],
        children: []
      }
    ]
  }
]

// 父为容器(有 BO_ROOT 可见内容), 子 子域A1 无可见内容 → 子上提
const nestedParentContainer = [
  {
    id: 'D_领域A', title: '领域A', enabled: true,
    directNodes: ['BO_ROOT'],
    children: [
      {
        id: 'SD_子域A1', title: '子域A1', enabled: true,
        containers: [{ id: 'C2', nodes: ['BO2'], enabled: false }],
        children: []
      }
    ]
  }
]

// 两侧都折叠到服务模块聚合节点 (领域/子领域为容器, 服务模块无可见子孙上提)
const bothSM = [
  {
    id: 'D1', title: '领域A', elementCode: 'DA', groupType: 'domain', enabled: true,
    children: [
      {
        id: 'SD1', title: '子领域A1', elementCode: 'SDA1', groupType: 'subDomain', enabled: true,
        children: [
          {
            id: 'SM1', title: '服务模块PM1', elementCode: 'PM1', groupType: 'serviceModule', enabled: true,
            containers: [{ id: 'bo1', elementCode: 'BO1', isVirtual: true, enabled: false, nodes: ['BO1'] }],
            children: []
          }
        ]
      }
    ]
  },
  {
    id: 'D2', title: '领域B', elementCode: 'DB', groupType: 'domain', enabled: true,
    children: [
      {
        id: 'SD2', title: '子领域B1', elementCode: 'SDB1', groupType: 'subDomain', enabled: true,
        children: [
          {
            id: 'SM2', title: '服务模块PM2', elementCode: 'PM2', groupType: 'serviceModule', enabled: true,
            containers: [{ id: 'bo3', elementCode: 'BO3', isVirtual: true, enabled: false, nodes: ['BO3'] }],
            children: []
          }
        ]
      }
    ]
  }
]

// 领域级折叠: 领域 collapsed=true 强制上提为聚合节点 (领域聚集所有子孙)
const bothDomain = JSON.parse(JSON.stringify(bothSM)).map(g => ({ ...g, collapsed: true }))

// 混合层级: 源折叠到领域级 (D1 无可见子孙 → 上提 COLLAPSE_D1, level 0),
//   目标折叠到子领域级 (SD2 无可见子孙 → 上提 COLLAPSE_SD2, level 1).
//   验证"源=领域, 目标=子领域 → 取较细层级=子领域 (level 1)".
const mixedDomainSubdomain = [
  {
    id: 'D1', title: '领域A', elementCode: 'DA', groupType: 'domain', enabled: true,
    containers: [{ id: 'bo1', elementCode: 'BO1', isVirtual: true, enabled: false, nodes: ['BO1'] }],
    children: []
  },
  {
    id: 'D2', title: '领域B', elementCode: 'DB', groupType: 'domain', enabled: true,
    children: [
      {
        id: 'SD2', title: '子领域B1', elementCode: 'SDB1', groupType: 'subDomain', enabled: true,
        containers: [{ id: 'bo3', elementCode: 'BO3', isVirtual: true, enabled: false, nodes: ['BO3'] }],
        children: []
      }
    ]
  }
]

const domainProducts = [
  { code: 'DA', name: '领域A', modules: [
    { code: 'SDA1', name: '子领域A1', submodules: [
      { code: 'PM1', name: '服务模块A1', businessObjects: [{ code: 'BO1', name: '对象A1' }, { code: 'BO2', name: '对象A2' }] }
    ] }
  ] },
  { code: 'DB', name: '领域B', modules: [
    { code: 'SDB1', name: '子领域B1', submodules: [
      { code: 'PM2', name: '服务模块B1', businessObjects: [{ code: 'BO3', name: '对象B1' }] }
    ] }
  ] }
]

// Excel 导入场景: 领域/子领域只有 name, 无 code 字段 (仅服务模块有 code).
//   [FIX 2026-08-06] 编码应从分组树 elementCode 回填, 否则折叠到领域/子领域时连线标签显示名称.
const domainProductsNoCodes = [
  { name: '领域A', modules: [
    { name: '子领域A1', submodules: [
      { name: '服务模块A1', code: 'PM1', businessObjects: [{ code: 'BO1', name: '对象A1' }, { code: 'BO2', name: '对象A2' }] }
    ] }
  ] },
  { name: '领域B', modules: [
    { name: '子领域B1', submodules: [
      { name: '服务模块B1', code: 'PM2', businessObjects: [{ code: 'BO3', name: '对象B1' }] }
    ] }
  ] }
]

describe('buildUpliftAncestorMap', () => {
  it('上提分组后, 其后代节点全部映射到聚合节点 (仅服务模块场景)', () => {
    const map = buildUpliftAncestorMap(onlySM)
    // 服务模块 PM1 上提 → 其后代 BO1/BO2 映射到 PM1 聚合节点
    expect(map.get('BO1')).toBe('COLLAPSE_SM1')
    expect(map.get('BO2')).toBe('COLLAPSE_SM1')
    // 领域A 为容器 (有可见内容 BO_ROOT), 不上提 → BO_ROOT 不应映射
    expect(map.has('BO_ROOT')).toBe(false)
  })

  it('最近上提祖先优先 (父容器 + 子上提): BO2 → 子上提聚合节点', () => {
    const map = buildUpliftAncestorMap(nestedParentContainer)
    expect(map.get('BO2')).toBe('COLLAPSE_SD_子域A1')
    // 父有可见内容 BO_ROOT, 不上提
    expect(map.has('BO_ROOT')).toBe(false)
  })
})

describe('remapLinksToVisibleAncestors', () => {
  it('指向被上提后代的分组连线端点重映射到聚合节点, 并调整颗粒度 label', () => {
    const links = [
      { sourceCode: 'BO2', targetCode: 'BO3', code: 'R1', relationCode: '调用' }
    ]
    const remapped = remapLinksToVisibleAncestors(links, onlySM, domainProducts)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('COLLAPSE_SM1')
    expect(remapped[0].targetCode).toBe('BO3')
    // 源折叠到服务模块(level 2), 目标可见 BO(level 3) → 取较细=BO(3), label=源BO-目标BO
    expect(remapped[0].code).toBe('BO2-BO3')
    expect(remapped[0].relationCode).toBe('调用')
  })

  it('两侧折叠到服务模块: 颗粒度=服务模块, label=源Code-目标Code拼接', () => {
    const links = [{ sourceCode: 'BO1', targetCode: 'BO3', code: 'R1', relationCode: '调用' }]
    const remapped = remapLinksToVisibleAncestors(links, bothSM, domainProducts)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('COLLAPSE_SM1')
    expect(remapped[0].targetCode).toBe('COLLAPSE_SM2')
    expect(remapped[0].code).toBe('PM1-PM2')
    expect(remapped[0].label).toBe('PM1-PM2')
    expect(remapped[0].sourceName).toBe('服务模块A1')
    expect(remapped[0].targetName).toBe('服务模块B1')
  })

  it('两侧折叠到领域: 颗粒度=领域, label=领域Code-领域Code拼接', () => {
    const links = [{ sourceCode: 'BO1', targetCode: 'BO3', code: 'R1' }]
    const remapped = remapLinksToVisibleAncestors(links, bothDomain, domainProducts)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('COLLAPSE_D1')
    expect(remapped[0].targetCode).toBe('COLLAPSE_D2')
    expect(remapped[0].code).toBe('DA-DB')
    expect(remapped[0].sourceName).toBe('领域A')
    expect(remapped[0].targetName).toBe('领域B')
  })

  it('混合层级: 源=领域, 目标=子领域 → 取较细层级=子领域, label=子领域Code-子领域Code', () => {
    const links = [{ sourceCode: 'BO1', targetCode: 'BO3', code: 'R1', relationCode: '调用' }]
    const remapped = remapLinksToVisibleAncestors(links, mixedDomainSubdomain, domainProducts)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('COLLAPSE_D1') // 源折叠到领域 (level 0)
    expect(remapped[0].targetCode).toBe('COLLAPSE_SD2') // 目标折叠到子领域 (level 1)
    // 颗粒度 = max(0,1) = 子领域 → 两端都取子领域祖先编码
    expect(remapped[0].code).toBe('SDA1-SDB1')
    expect(remapped[0].label).toBe('SDA1-SDB1')
    expect(remapped[0].sourceName).toBe('子领域A1')
    expect(remapped[0].targetName).toBe('子领域B1')
    expect(remapped[0].relationCode).toBe('调用')
  })

  it('Excel场景: domainProducts 领域/子领域无 code, 从分组树 elementCode 回填编码', () => {
    // bothDomain 分组树含 elementCode (DA/SDA1/PM1, DB/SDB1/PM2)
    const links = [{ sourceCode: 'BO1', targetCode: 'BO3', code: 'R1' }]
    const remapped = remapLinksToVisibleAncestors(links, bothDomain, domainProductsNoCodes)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('COLLAPSE_D1')
    expect(remapped[0].targetCode).toBe('COLLAPSE_D2')
    // 即使 domainProducts 领域/子领域缺 code, 也应显示编码 (由分组树 elementCode 回填)
    expect(remapped[0].code).toBe('DA-DB')
    expect(remapped[0].label).toBe('DA-DB')
    expect(remapped[0].sourceName).toBe('领域A')
    expect(remapped[0].targetName).toBe('领域B')
  })

  it('未重映射的连线 (两端均可见 BO) 保留原始编码', () => {
    const links = [{ sourceCode: 'BO_ROOT', targetCode: 'BO3', code: 'R1', relationCode: '调用' }]
    const remapped = remapLinksToVisibleAncestors(links, onlySM, domainProducts)
    expect(remapped.length).toBe(1)
    expect(remapped[0].sourceCode).toBe('BO_ROOT')
    expect(remapped[0].targetCode).toBe('BO3')
    expect(remapped[0].code).toBe('R1')
  })

  it('两端上提到同一聚合节点 → 丢弃 (自环)', () => {
    const links = [
      { sourceCode: 'BO1', targetCode: 'BO2', code: 'R2' } // 都在 PM1
    ]
    const remapped = remapLinksToVisibleAncestors(links, onlySM)
    expect(remapped.length).toBe(0)
  })

  it('无上提分组时原样返回', () => {
    const noUplift = [
      { id: 'D_X', title: 'X', enabled: true, directNodes: ['A'], children: [] }
    ]
    const links = [{ sourceCode: 'A', targetCode: 'B' }]
    const remapped = remapLinksToVisibleAncestors(links, noUplift)
    expect(remapped).toEqual(links)
  })

  it('upliftNodeId 编码稳定且与 groupedLayout 一致', () => {
    expect(upliftNodeId({ id: 'D_领域A' })).toBe('COLLAPSE_D_领域A')
  })
})

describe('fuseLinks', () => {
  it('相同 (源, 目标) 对 → 只保留一条连线', () => {
    const links = [
      { sourceCode: 'COLLAPSE_A', targetCode: 'B', label: 'L1' },
      { sourceCode: 'COLLAPSE_A', targetCode: 'B', label: 'L2' },
      { sourceCode: 'COLLAPSE_A', targetCode: 'B', label: 'L3' }
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].label).toBe('L1') // 保留组内首条
    expect(fused[0].relationDirection).toBeUndefined() // 同向不标记双向
  })

  it('源->目标 与 目标->源 同时存在 → 合并为双向 (A <-> B)', () => {
    const links = [
      { sourceCode: 'A', targetCode: 'B', label: 'AB', relationDirection: 'PUSH' },
      { sourceCode: 'B', targetCode: 'A', label: 'BA', relationDirection: 'PULL' }
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].sourceCode).toBe('A')
    expect(fused[0].targetCode).toBe('B')
    expect(fused[0].relationDirection).toBe('BIDIRECTIONAL')
  })

  it('任一子连线明确双向 → 组合并标记为双向', () => {
    const links = [
      { sourceCode: 'A', targetCode: 'B', relationDirection: 'BIDIRECTIONAL' },
      { sourceCode: 'A', targetCode: 'B', relationDirection: 'PUSH' }
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].relationDirection).toBe('BIDIRECTIONAL')
  })

  it('不同节点对互不影响, 各自独立融合', () => {
    const links = [
      { sourceCode: 'A', targetCode: 'B', relationDirection: 'PUSH' },
      { sourceCode: 'B', targetCode: 'A', relationDirection: 'PULL' },
      { sourceCode: 'C', targetCode: 'D', relationDirection: 'PUSH' },
      { sourceCode: 'C', targetCode: 'D', relationDirection: 'PUSH' }
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(2)
    const bidis = fused.filter(l => l.relationDirection === 'BIDIRECTIONAL')
    expect(bidis.length).toBe(1)
    expect(bidis[0].sourceCode).toBe('A')
    expect(bidis[0].targetCode).toBe('B')
  })

  it('空数组原样返回', () => {
    expect(fuseLinks([])).toEqual([])
  })
})