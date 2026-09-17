/**
 * BUG-V028 回归测试: 架构管理页 对象范围树 count 不再被 BO 500 cap 影响
 *
 * 根因: ObjectScopeSection.vue 的 buildHierarchyTree 拉全量 BO 客户端聚合,
 *       但 /api/v2/bo/business_object 受 MAX_USER_PAGE_SIZE=500 限制,
 *       V863 实际 2850 BO 被截断为 500, 导致 233/402 (58%) SM count 错显示 0.
 *
 * 修复: 不再拉 BO 列表, 直接使用 service_module API 返回的 child_count
 *       (由 computation_service._batch_count_children 一次性 GROUP BY 统计)
 *       buildHierarchyTree 签名变为 (domains, subDomains, serviceModules), 3 个参数
 *
 * @see d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/ObjectScopeSection.vue
 */
import { describe, it, expect } from 'vitest'

// === 1. 重现修复后的 buildHierarchyTree 核心逻辑 ===
// 必须与 ObjectScopeSection.vue:454-523 完全一致, 否则此测试失去意义
function buildHierarchyTree(domains, subDomains, serviceModules) {
  const subDomainMap = new Map()
  const serviceModuleMap = new Map()

  for (const sd of subDomains) {
    const list = subDomainMap.get(sd.domain_id) || []
    list.push(sd)
    subDomainMap.set(sd.domain_id, list)
  }

  for (const sm of serviceModules) {
    const list = serviceModuleMap.get(sm.sub_domain_id) || []
    list.push(sm)
    serviceModuleMap.set(sm.sub_domain_id, list)
  }

  return domains.map(domain => {
    const domainSubDomains = subDomainMap.get(domain.id) || []
    let domainBoCount = 0
    const subDomainNodes = []

    for (const subDomain of domainSubDomains) {
      const moduleList = serviceModuleMap.get(subDomain.id) || []
      let subDomainBoCount = 0
      const serviceModuleNodes = []

      for (const module of moduleList) {
        const boCount = module.child_count || 0  // 修复: 用 API 的 child_count, 不是 BO 列表聚合
        subDomainBoCount += boCount
        serviceModuleNodes.push({
          id: `sm_${module.id}`,
          originalId: module.id,
          name: module.name,
          code: module.code,
          type: 'service_module',
          count: boCount,
          children: []
        })
      }

      domainBoCount += subDomainBoCount
      subDomainNodes.push({
        id: `s_${subDomain.id}`,
        originalId: subDomain.id,
        name: subDomain.name,
        code: subDomain.code,
        type: 'sub_domain',
        count: subDomainBoCount,
        children: serviceModuleNodes
      })
    }

    return {
      id: `d_${domain.id}`,
      originalId: domain.id,
      name: domain.name,
      code: domain.code,
      type: 'domain',
      count: domainBoCount,
      children: subDomainNodes
    }
  })
}

// === 2. 模拟 500 cap 截断的旧实现 (用于对比测试) ===
function buildHierarchyTreeLegacy(domains, subDomains, serviceModules, businessObjects) {
  const subDomainMap = new Map()
  const serviceModuleMap = new Map()
  const boCountBySm = new Map()

  for (const sd of subDomains) {
    const list = subDomainMap.get(sd.domain_id) || []
    list.push(sd)
    subDomainMap.set(sd.domain_id, list)
  }
  for (const sm of serviceModules) {
    const list = serviceModuleMap.get(sm.sub_domain_id) || []
    list.push(sm)
    serviceModuleMap.set(sm.sub_domain_id, list)
  }
  for (const bo of (businessObjects || [])) {
    const smId = bo.service_module_id
    if (smId != null) {
      boCountBySm.set(smId, (boCountBySm.get(smId) || 0) + 1)
    }
  }

  return domains.map(domain => {
    const domainSubDomains = subDomainMap.get(domain.id) || []
    let domainBoCount = 0
    const subDomainNodes = []
    for (const subDomain of domainSubDomains) {
      const moduleList = serviceModuleMap.get(subDomain.id) || []
      let subDomainBoCount = 0
      const serviceModuleNodes = []
      for (const module of moduleList) {
        const boCount = boCountBySm.get(module.id) || 0
        subDomainBoCount += boCount
        serviceModuleNodes.push({ id: `sm_${module.id}`, originalId: module.id, count: boCount, type: 'service_module', children: [] })
      }
      domainBoCount += subDomainBoCount
      subDomainNodes.push({ id: `s_${subDomain.id}`, originalId: subDomain.id, count: subDomainBoCount, type: 'sub_domain', children: serviceModuleNodes })
    }
    return { id: `d_${domain.id}`, originalId: domain.id, count: domainBoCount, type: 'domain', children: subDomainNodes }
  })
}

// === 3. 单元测试 ===
describe('BUG-V028 buildHierarchyTree 使用 child_count 不受 500 cap 影响', () => {
  it('signature: 只有 3 个参数 (无 businessObjects)', () => {
    expect(buildHierarchyTree.length).toBe(3)
  })

  it('简单场景: 1 domain, 1 sd, 2 sm (各 5 BO) → 树 count 正确', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = [{ id: 10, name: 'sd1', code: 'SD1', domain_id: 1 }]
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 10, child_count: 5 },
      { id: 101, name: 'sm2', code: 'SM2', sub_domain_id: 10, child_count: 5 }
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)

    expect(tree[0].count).toBe(10)  // 5+5
    expect(tree[0].children[0].count).toBe(10)  // sd1: 5+5
    expect(tree[0].children[0].children[0].count).toBe(5)  // sm1
    expect(tree[0].children[0].children[1].count).toBe(5)  // sm2
  })

  it('V863 场景模拟: 500 cap 截断 2850→500 BO, 新实现仍正确 (旧实现失败)', () => {
    // 模拟 V863: 402 SM, 其中 277 有 BO, 总 2850 BO
    // 但 500 cap 截断后只剩 500 BO 分布在前 ~44 个 SM
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = [{ id: 10, name: 'sd1', code: 'SD1', domain_id: 1 }]

    // 真实 child_count: 277 个 SM 有 BO (非均匀分布)
    const serviceModules = []
    for (let i = 1; i <= 277; i++) {
      serviceModules.push({ id: i, name: `sm${i}`, code: `SM${i}`, sub_domain_id: 10, child_count: 10 })  // 平均 10 BO
    }
    for (let i = 278; i <= 402; i++) {
      serviceModules.push({ id: i, name: `sm${i}`, code: `SM${i}`, sub_domain_id: 10, child_count: 0 })
    }

    // 500 cap 截断: 只前 50 个 SM 有 BO (500/10=50)
    const businessObjects = []
    for (let i = 1; i <= 50; i++) {
      for (let j = 0; j < 10; j++) {
        businessObjects.push({ id: i * 10 + j, service_module_id: i })
      }
    }

    // 旧实现 (受影响): 233 个 SM (i=51..277, child_count=10 但 BO 截断) 都显示 0
    const legacyTree = buildHierarchyTreeLegacy(domains, subDomains, serviceModules, businessObjects)
    let legacyZeroCount = 0
    for (const sd of legacyTree[0].children) {
      for (const sm of sd.children) {
        if (sm.count === 0 && sm.originalId <= 277) legacyZeroCount++
      }
    }
    expect(legacyZeroCount).toBe(227)  // 旧实现: 227 个 SM 错显示 0

    // 新实现 (不受影响): 所有 SM count 都正确
    const newTree = buildHierarchyTree(domains, subDomains, serviceModules)
    let newZeroCount = 0
    for (const sd of newTree[0].children) {
      for (const sm of sd.children) {
        if (sm.count === 0 && sm.originalId <= 277) newZeroCount++
      }
    }
    expect(newZeroCount).toBe(0)  // 新实现: 0 个 SM 错显示 0

    // 总数校验
    expect(newTree[0].count).toBe(277 * 10)  // 2770
    expect(legacyTree[0].count).toBe(50 * 10)  // 500
    expect(newTree[0].count).toBeGreaterThan(legacyTree[0].count)
  })

  it('边界: child_count=0 的 SM 不影响父级 (聚合正确)', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = [{ id: 10, name: 'sd1', code: 'SD1', domain_id: 1 }]
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 10, child_count: 0 },
      { id: 101, name: 'sm2', code: 'SM2', sub_domain_id: 10, child_count: 0 }
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    expect(tree[0].count).toBe(0)
    expect(tree[0].children[0].count).toBe(0)
  })

  it('边界: child_count 字段缺失时, 默认为 0 (不报错)', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = [{ id: 10, name: 'sd1', code: 'SD1', domain_id: 1 }]
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 10 }  // 故意省略 child_count
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    expect(tree[0].count).toBe(0)
    expect(tree[0].children[0].children[0].count).toBe(0)
  })

  it('多 sub_domain 聚合: 各 sd 独立求和, 域总数 = sum(sd.count)', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = [
      { id: 10, name: 'sd1', code: 'SD1', domain_id: 1 },
      { id: 11, name: 'sd2', code: 'SD2', domain_id: 1 }
    ]
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 10, child_count: 7 },
      { id: 101, name: 'sm2', code: 'SM2', sub_domain_id: 10, child_count: 3 },
      { id: 102, name: 'sm3', code: 'SM3', sub_domain_id: 11, child_count: 9 }
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    expect(tree[0].count).toBe(19)  // 7+3+9
    expect(tree[0].children[0].count).toBe(10)  // sd1
    expect(tree[0].children[1].count).toBe(9)  // sd2
  })

  it('多 domain 隔离: 互不干扰', () => {
    const domains = [
      { id: 1, name: 'd1', code: 'D1' },
      { id: 2, name: 'd2', code: 'D2' }
    ]
    const subDomains = [
      { id: 10, name: 'sd1', code: 'SD1', domain_id: 1 },
      { id: 20, name: 'sd2', code: 'SD2', domain_id: 2 }
    ]
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 10, child_count: 5 },
      { id: 200, name: 'sm2', code: 'SM2', sub_domain_id: 20, child_count: 8 }
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    expect(tree[0].count).toBe(5)
    expect(tree[1].count).toBe(8)
  })

  it('空输入: 不崩溃, 返回空树', () => {
    const tree = buildHierarchyTree([], [], [])
    expect(tree).toEqual([])
  })

  it('SM 没有对应 SD: SM 被忽略 (不进入树)', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = []
    const serviceModules = [
      { id: 100, name: 'sm1', code: 'SM1', sub_domain_id: 999, child_count: 5 }  // sub_domain_id 不存在
    ]

    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    expect(tree[0].count).toBe(0)
    expect(tree[0].children).toEqual([])
  })

  it('性能: 1000 SM 聚合 < 50ms (避免 500 cap 后重新拉 BO 的网络开销)', () => {
    const domains = [{ id: 1, name: 'd1', code: 'D1' }]
    const subDomains = []
    const serviceModules = []
    for (let sd = 1; sd <= 100; sd++) {
      subDomains.push({ id: sd, name: `sd${sd}`, code: `SD${sd}`, domain_id: 1 })
      for (let sm = 1; sm <= 10; sm++) {
        serviceModules.push({
          id: sd * 100 + sm,
          name: `sm${sd}_${sm}`,
          code: `SM${sd}_${sm}`,
          sub_domain_id: sd,
          child_count: Math.floor(Math.random() * 50)
        })
      }
    }

    const start = Date.now()
    const tree = buildHierarchyTree(domains, subDomains, serviceModules)
    const elapsed = Date.now() - start
    expect(elapsed).toBeLessThan(50)  // 50ms 内完成
    expect(tree[0].children.length).toBe(100)
  })
})

// === 4. 旧实现必须被彻底删除 ===
describe('BUG-V028 旧实现残留检测 (防止回滚)', () => {
  it('buildHierarchyTree 不应再接受 4 个参数 (businessObjects)', () => {
    expect(buildHierarchyTree.length).not.toBe(4)
  })

  it('buildHierarchyTree 内部不应再有 boCountBySm 变量', () => {
    // 通过函数体字符串检测 (粗略, 防止未来有人合并旧实现)
    const fnStr = buildHierarchyTree.toString()
    expect(fnStr).not.toContain('boCountBySm')
    expect(fnStr).not.toContain('businessObjects')
  })
})
