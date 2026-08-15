/**
 * expandLevel.spec - 展开层级共享工具单元测试
 *
 * 覆盖 [SCOPE-DEFAULT 2026-08-08] 新增行为：
 *   - expandGroupsToLevel / applyDefaultExpandByScope 返回 { matched, collapsedCount }
 *   - 非全展开却 0 折叠 / 范围内 0 命中 → console.warn 告警 (静默失败可观测)
 *   - 范围默认折叠: 范围内→服务模块, 范围外→子领域
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  EXPAND_LEVELS,
  groupTypeLevel,
  groupLevelOf,
  isSubtreeInScope,
  expandGroupsToLevel,
  applyDefaultExpandByScope,
  computeDefaultExpandLevel,
  applyDefaultExpandByCount
} from '../expandLevel.js'

afterEach(() => {
  vi.restoreAllMocks()
})

// 构造三层分组树: domain → subDomain → serviceModule (+ 更深 BO 容器)
function buildTree() {
  return [
    {
      elementCode: 'SC', groupType: 'domain', children: [
        {
          elementCode: 'SCP', groupType: 'subDomain', children: [
            { elementCode: 'SM1', groupType: 'serviceModule', children: [] },
            { elementCode: 'SM2', groupType: 'serviceModule', children: [] }
          ]
        },
        {
          elementCode: 'SALE', groupType: 'subDomain', children: [
            { elementCode: 'SM3', groupType: 'serviceModule', children: [] }
          ]
        }
      ]
    }
  ]
}

describe('groupTypeLevel / groupLevelOf', () => {
  it('映射 domain=0/subDomain=1/serviceModule=2, 其余=3', () => {
    expect(groupTypeLevel('domain')).toBe(0)
    expect(groupTypeLevel('subDomain')).toBe(1)
    expect(groupTypeLevel('serviceModule')).toBe(2)
    expect(groupTypeLevel('custom')).toBe(3)
    expect(groupLevelOf({ groupType: 'domain' })).toBe(0)
    expect(groupLevelOf({ type: 'SERVICE_MODULE' })).toBe(2)
  })
})

describe('isSubtreeInScope', () => {
  it('命中容器自身 / containers / children / directNodes 任一编码即 true', () => {
    const g = {
      elementCode: 'SC', children: [
        { elementCode: 'SCP', directNodes: ['BO1', 'BO2'] }
      ]
    }
    expect(isSubtreeInScope(g, new Set(['BO2']))).toBe(true)
    expect(isSubtreeInScope(g, new Set(['SCP']))).toBe(true)
    expect(isSubtreeInScope(g, new Set(['BO9']))).toBe(false)
    expect(isSubtreeInScope(g, new Set([]))).toBe(false)
  })
})

describe('expandGroupsToLevel', () => {
  it('展开到业务对象: 全部 collapsed=false, 返回 collapsedCount=0', () => {
    const tree = buildTree()
    const r = expandGroupsToLevel(tree, 'businessObject')
    expect(r.collapsedCount).toBe(0)
    expect(tree[0].collapsed).toBe(false)
    expect(tree[0].children[0].collapsed).toBe(false)
  })

  it('展开到服务模块: serviceModule 及更深折叠, 返回折叠计数', () => {
    const tree = buildTree()
    const r = expandGroupsToLevel(tree, 'serviceModule')
    expect(r.collapsedCount).toBeGreaterThan(0)
    expect(tree[0].collapsed).toBe(false)       // domain 不折叠
    expect(tree[0].children[0].collapsed).toBe(false) // subDomain 不折叠
    expect(tree[0].children[0].children[0].collapsed).toBe(true) // serviceModule 折叠
  })

  it('展开到领域: 领域自身折叠为聚合节点, 下级全折叠', () => {
    const tree = buildTree()
    const r = expandGroupsToLevel(tree, 'domain')
    // 语义: "展开到领域" → 领域作为聚合节点展示, 自身 collapsed=true (groupTypeLevel>=0)
    expect(tree[0].collapsed).toBe(true)
    expect(tree[0].children[0].collapsed).toBe(true) // subDomain 折叠
    expect(r.collapsedCount).toBeGreaterThan(0)
  })

  it('非全展开却 0 折叠 → console.warn 告警', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const r = expandGroupsToLevel([], 'serviceModule')
    expect(r.collapsedCount).toBe(0)
    expect(spy).toHaveBeenCalled()
  })

  it('[VIS-RESET 2026-08-14] 默认不重置用户图例隐藏 (visible=false 保留)', () => {
    const tree = buildTree()
    // 模拟图例隐藏: 隐藏 SALE 子领域及其下 SM3
    tree[0].children[1].visible = false
    tree[0].children[1].children[0].visible = false
    const r = expandGroupsToLevel(tree, 'subDomain')
    // 渲染层每次重算/默认展开不重置用户主动隐藏 (2026-08-14 修复: 隐藏外部领域云后
    // 双击服务模块不再重显)
    expect(tree[0].children[1].visible).toBe(false)
    expect(tree[0].children[1].children[0].visible).toBe(false)
    expect(r.collapsedCount).toBeGreaterThan(0)
  })

  it('[VIS-RESET 2026-08-12] 显式切换全局展开层级 ({ resetVisible: true }) 时重置图例隐藏', () => {
    const tree = buildTree()
    // 模拟图例隐藏: 隐藏 SALE 子领域及其下 SM3
    tree[0].children[1].visible = false
    tree[0].children[1].children[0].visible = false
    const r = expandGroupsToLevel(tree, 'subDomain', { resetVisible: true })
    // 仅"用户显式切换全局展开层级"的操作方传 resetVisible 才重置 (2026-08-12 旧规则)
    expect(tree[0].children[1].visible).toBe(true)
    expect(tree[0].children[1].children[0].visible).toBe(true)
    expect(r.collapsedCount).toBeGreaterThan(0)
  })
})

describe('applyDefaultExpandByScope', () => {
  const inScope = (g) => g.elementCode === 'SC' || g.elementCode === 'SCP'
      || g.elementCode === 'SM1' || g.elementCode === 'SM2'

  it('范围内分组折叠到服务模块, 范围外折叠到子领域', () => {
    const tree = buildTree()
    const r = applyDefaultExpandByScope(tree, inScope)
    // 范围内的 subDomain(SCP) 不折叠(target=serviceModule), 其 serviceModule 折叠
    const scp = tree[0].children[0]
    expect(scp.collapsed).toBe(false)
    expect(scp.children[0].collapsed).toBe(true)   // SM1 折叠
    // 范围外的 subDomain(SALE) 折叠到子领域(target=1)
    expect(tree[0].children[1].collapsed).toBe(true)
    expect(r.matched).toBeGreaterThan(0)
    expect(r.collapsedCount).toBeGreaterThan(0)
  })

  it('无对象范围(未传入谓词) → 不折叠不告警, 返回 0', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const tree = buildTree()
    const r = applyDefaultExpandByScope(tree, undefined)
    expect(r.collapsedCount).toBe(0)
    expect(r.matched).toBe(0)
    expect(spy).not.toHaveBeenCalled()
  })

  it('谓词无命中(范围编码不匹配) → 中止折叠并 console.warn', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const tree = buildTree()
    const r = applyDefaultExpandByScope(tree, () => false)
    expect(r.collapsedCount).toBe(0)
    expect(r.matched).toBe(0)
    expect(spy).toHaveBeenCalled()
    // 不匹配时应中止默认折叠, 树节点 collapsed 保持未设置(不折叠)
    expect(tree[0].collapsed).toBeFalsy()
    expect(tree[0].children[0].collapsed).toBeFalsy()
  })
})

// [ELK-GROUP 2026-08-12] 系统自动分组: 无关系(inner)/有关系(boundary), _elkGroup 标记.
//   它们是 ELK 布局的系统分组, 非用户可折叠层级, 展开/折叠时须保持容器形态(不折叠为聚合节点),
//   且其默认 visible=false 表示"无边框但节点仍渲染"(系统语义), 不被展开层级重置.
function buildElkTree() {
  return [
    {
      elementCode: 'SC', groupType: 'domain', children: [
        {
          elementCode: 'SCP', groupType: 'subDomain', children: [
            {
              elementCode: 'SM1', groupType: 'serviceModule',
              children: [
                { id: 'SM1_inner', elementCode: 'SM1_inner', groupType: 'custom', _elkGroup: 'inner', visible: false, directNodes: ['N1', 'N2'] },
                { id: 'SM1_boundary', elementCode: 'SM1_boundary', groupType: 'custom', _elkGroup: 'boundary', visible: false, directNodes: ['N3'] }
              ]
            }
          ]
        }
      ]
    }
  ]
}

describe('ELK 系统自动分组 (无关系/有关系)', () => {
  it('expandGroupsToLevel 不折叠系统自动分组(_elkGroup), 保持容器形态', () => {
    const tree = buildElkTree()
    expandGroupsToLevel(tree, 'subDomain')
    const sm = tree[0].children[0].children[0]     // SM1
    const inner = sm.children[0]
    const boundary = sm.children[1]
    expect(sm.collapsed).toBe(true)                // 普通 serviceModule 折叠
    expect(inner.collapsed).toBeFalsy()            // ELK inner 不折叠
    expect(boundary.collapsed).toBeFalsy()         // ELK boundary 不折叠
  })

  it('expandGroupsToLevel 默认不重置任何 visible (含 ELK 系统自动分组)', () => {
    const tree = buildElkTree()
    expandGroupsToLevel(tree, 'businessObject')
    const sm = tree[0].children[0].children[0]
    expect(sm.children[0].visible).toBe(false)     // ELK inner visible=false 保留
    expect(sm.children[1].visible).toBe(false)     // ELK boundary visible=false 保留
  })

  it('applyDefaultExpandByScope 不折叠系统自动分组', () => {
    const tree = buildElkTree()
    const r = applyDefaultExpandByScope(tree, (g) => ['SC', 'SCP', 'SM1'].includes(g.elementCode))
    const sm = tree[0].children[0].children[0]
    expect(sm.collapsed).toBe(true)                // 范围内 SM1 折叠到服务模块
    expect(sm.children[0].collapsed).toBeFalsy()   // ELK inner 不折叠
    expect(sm.children[1].collapsed).toBeFalsy()   // ELK boundary 不折叠
    expect(r.collapsedCount).toBeGreaterThan(0)
  })
})

// [DEFAULT-LEVEL 2026-08-12] 系统默认展开层级（按分组数量自适应）
//   图表初始展示时, 从粗到细找第一个"分组数 > 1"的层级:
//     >1 领域→领域; 否则 >1 子领域→子领域; 否则 >1 服务模块→服务模块; 否则→业务对象
describe('computeDefaultExpandLevel / applyDefaultExpandByCount', () => {
  const domain = (code, children = []) => ({ elementCode: code, groupType: 'domain', children })
  const subDomain = (code, children = []) => ({ elementCode: code, groupType: 'subDomain', children })
  const serviceModule = (code) => ({ elementCode: code, groupType: 'serviceModule', children: [] })

  it('空/非数组 → 业务对象(全展开)', () => {
    expect(computeDefaultExpandLevel(undefined)).toBe('businessObject')
    expect(computeDefaultExpandLevel([])).toBe('businessObject')
  })

  it('>1 领域 → 展开到领域', () => {
    const tree = [
      domain('D1', [subDomain('S1')]),
      domain('D2', [subDomain('S2')])
    ]
    expect(computeDefaultExpandLevel(tree)).toBe('domain')
  })

  it('单领域 + >1 子领域 → 展开到子领域', () => {
    const tree = [domain('D1', [subDomain('S1'), subDomain('S2')])]
    expect(computeDefaultExpandLevel(tree)).toBe('subDomain')
  })

  it('单领域 + 单子领域 + >1 服务模块 → 展开到服务模块', () => {
    const tree = [domain('D1', [subDomain('S1', [serviceModule('SM1'), serviceModule('SM2')])])]
    expect(computeDefaultExpandLevel(tree)).toBe('serviceModule')
  })

  it('单领域 + 单子领域 + 单服务模块 → 展开到业务对象', () => {
    const tree = [domain('D1', [subDomain('S1', [serviceModule('SM1')])])]
    expect(computeDefaultExpandLevel(tree)).toBe('businessObject')
  })

  it('统计跨 children/containers 递归 (混合嵌套)', () => {
    // domain(1) 下: 2 个 subDomain(一个在 containers) → 展开到子领域
    const tree = [{
      elementCode: 'D1', groupType: 'domain',
      children: [{ elementCode: 'S1', groupType: 'subDomain', children: [] }],
      containers: [{ elementCode: 'S2', groupType: 'subDomain', children: [] }]
    }]
    expect(computeDefaultExpandLevel(tree)).toBe('subDomain')
  })

  it('ELK 系统自动分组(groupType=custom, level 3)不参与计数 → 不影响结果', () => {
    const tree = [domain('D1', [
      subDomain('S1', [
        { elementCode: 'SM1', groupType: 'serviceModule', children: [
          { id: 'inner', groupType: 'custom', _elkGroup: 'inner', children: [] },
          { id: 'boundary', groupType: 'custom', _elkGroup: 'boundary', children: [] }
        ] }
      ])
    ])]
    // 服务模块数=1 (ELK inner/boundary 不算), 单领域单子领域单服务模块 → 业务对象
    expect(computeDefaultExpandLevel(tree)).toBe('businessObject')
  })

  it('applyDefaultExpandByCount 返回 level 并按层级就地折叠', () => {
    const tree = [domain('D1', [subDomain('S1', [serviceModule('SM1'), serviceModule('SM2')])])]
    const r = applyDefaultExpandByCount(tree)
    expect(r.level).toBe('serviceModule')
    expect(r.collapsedCount).toBeGreaterThan(0)
    // 展开到服务模块: domain/subDomain 容器, serviceModule 折叠
    expect(tree[0].collapsed).toBe(false)
    expect(tree[0].children[0].collapsed).toBe(false)
    expect(tree[0].children[0].children[0].collapsed).toBe(true)
  })
})

describe('EXPAND_LEVELS', () => {
  it('层级定义顺序 domain<subDomain<serviceModule<businessObject', () => {
    expect(EXPAND_LEVELS.map(x => x.level)).toEqual([0, 1, 2, 3])
    expect(EXPAND_LEVELS.map(x => x.key)).toEqual(
      ['domain', 'subDomain', 'serviceModule', 'businessObject']
    )
  })
})
