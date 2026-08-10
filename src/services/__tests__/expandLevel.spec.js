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
  applyDefaultExpandByScope
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

describe('EXPAND_LEVELS', () => {
  it('层级定义顺序 domain<subDomain<serviceModule<businessObject', () => {
    expect(EXPAND_LEVELS.map(x => x.level)).toEqual([0, 1, 2, 3])
    expect(EXPAND_LEVELS.map(x => x.key)).toEqual(
      ['domain', 'subDomain', 'serviceModule', 'businessObject']
    )
  })
})
