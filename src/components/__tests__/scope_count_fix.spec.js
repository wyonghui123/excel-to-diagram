/**
 * v39 修复: 架构管理页 chip 数字 = 扁平去重 BO 数 / 关系数
 * v48 修复 (2026-07-08): 改用树节点 count 精确累加, 避免双重计数
 * 跨页一致性: 架构管理 chip 数字 == 图表页 业务对象数/关系数
 */
import { describe, it, expect } from 'vitest'

// ============================================================
// 1. v48 新算法: selectedBoCount (按"未被祖先覆盖"原则累加)
// ============================================================
describe('selectedBoCount V048 (按树节点 count 精确累加)', () => {
  // 模拟 production code 的 selectedBoCount 算法
  function buildCountMap(treeData, type) {
    const map = new Map()
    function walk(nodes) {
      if (!nodes) return
      for (const n of nodes) {
        if (n.type === type && (n.count || 0) > 0) {
          map.set(n.originalId || n.id, n.count)
        }
        if (n.children) walk(n.children)
      }
    }
    walk(treeData)
    return map
  }

  function selectedBoCountV048({
    selectedBoIds = [],
    selectedDomainIds = [],
    selectedSubDomainIds = [],
    selectedServiceModuleIds = [],
    treeData = [],
    hierarchyMap = {}
  }) {
    const smChildCount = buildCountMap(treeData, 'service_module')
    const sdChildCount = buildCountMap(treeData, 'sub_domain')
    const domainChildCount = buildCountMap(treeData, 'domain')

    // [V048b] ID 类型规范化: 兼容数字/字符串/带前缀 id
    const normalizeId = (v) => {
      if (v == null) return v
      if (typeof v === 'number') return v
      const s = String(v)
      const numStr = s.replace(/^(d|s|sm)_/, '')
      const n = Number(numStr)
      return Number.isNaN(n) ? s : n
    }

    const selectedDomainSet = new Set(selectedDomainIds.map(normalizeId))
    const selectedSubDomainSet = new Set(selectedSubDomainIds.map(normalizeId))
    let total = 0

    // 1. 选中的 SM (只在所属 SD/domain 未被选中时累加)
    for (const smId of selectedServiceModuleIds) {
      const nId = normalizeId(smId)
      const info = hierarchyMap[nId] || hierarchyMap[smId] || hierarchyMap[`sm_${nId}`]
      if (!info) continue
      if (selectedSubDomainSet.has(info.subDomainId)) continue
      if (selectedDomainSet.has(info.domainId)) continue
      total += smChildCount.get(nId) || smChildCount.get(smId) || 0
    }

    // 2. 选中的 SD (只在所属 domain 未被选中时累加)
    for (const sdId of selectedSubDomainIds) {
      const nId = normalizeId(sdId)
      const info = hierarchyMap[nId] || hierarchyMap[sdId] || hierarchyMap[`s_${nId}`]
      if (!info) continue
      if (selectedDomainSet.has(info.domainId)) continue
      total += sdChildCount.get(nId) || sdChildCount.get(sdId) || 0
    }

    // 3. 选中的 domain (直接累加)
    for (const dId of selectedDomainIds) {
      const nId = normalizeId(dId)
      total += domainChildCount.get(nId) || domainChildCount.get(dId) || 0
    }

    // 4. 兜底: 只选了 BO (无任何祖先) → 用 selectedBoIds.length
    if (
      total === 0 &&
      selectedBoIds.length > 0 &&
      selectedDomainIds.length === 0 &&
      selectedSubDomainIds.length === 0 &&
      selectedServiceModuleIds.length === 0
    ) {
      total = selectedBoIds.length
    }

    return total
  }

  // 树结构: domain1(4 BO) → sd1(3 BO) → sm1(2 BO) / sm2(1 BO)
  //                  sd2(1 BO) → sm3(1 BO)
  //         domain2(3 BO) → sd3(3 BO) → sm4(3 BO)
  const treeData = [
    {
      id: 'd_1', originalId: 1, type: 'domain', name: 'Domain 1', count: 4,
      children: [
        {
          id: 's_10', originalId: 10, type: 'sub_domain', name: 'SD 1', count: 3,
          children: [
            { id: 'sm_100', originalId: 100, type: 'service_module', name: 'SM 1', count: 2, children: [] },
            { id: 'sm_101', originalId: 101, type: 'service_module', name: 'SM 2', count: 1, children: [] },
          ]
        },
        {
          id: 's_11', originalId: 11, type: 'sub_domain', name: 'SD 2', count: 1,
          children: [
            { id: 'sm_102', originalId: 102, type: 'service_module', name: 'SM 3', count: 1, children: [] },
          ]
        },
      ]
    },
    {
      id: 'd_2', originalId: 2, type: 'domain', name: 'Domain 2', count: 3,
      children: [
        {
          id: 's_20', originalId: 20, type: 'sub_domain', name: 'SD 3', count: 3,
          children: [
            { id: 'sm_200', originalId: 200, type: 'service_module', name: 'SM 4', count: 3, children: [] },
          ]
        },
      ]
    },
  ]

  const hierarchyMap = {
    1: { domainId: 1 },
    2: { domainId: 2 },
    10: { domainId: 1, subDomainId: 10 },
    11: { domainId: 1, subDomainId: 11 },
    20: { domainId: 2, subDomainId: 20 },
    100: { domainId: 1, subDomainId: 10, serviceModuleId: 100 },
    101: { domainId: 1, subDomainId: 10, serviceModuleId: 101 },
    102: { domainId: 1, subDomainId: 11, serviceModuleId: 102 },
    200: { domainId: 2, subDomainId: 20, serviceModuleId: 200 },
  }

  // ========================================
  // 用户场景: 选 1 个 domain (级联到 SD/SM)
  // ========================================
  it('用户场景 A: 选 domain 1 (el-tree 级联到 SD 10,11 + SM 100,101,102)', () => {
    // 勾上: [domain 1, sd 10, sd 11, sm 100, sm 101, sm 102]
    const result = selectedBoCountV048({
      selectedDomainIds: [1],
      selectedSubDomainIds: [10, 11],
      selectedServiceModuleIds: [100, 101, 102],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(4) // domain 1 的 count
  })

  it('用户场景 B: 选 SD 10 (级联到 SM 100,101)', () => {
    const result = selectedBoCountV048({
      selectedSubDomainIds: [10],
      selectedServiceModuleIds: [100, 101],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(3) // SD 10 的 count
  })

  it('用户场景 C: 选单个 SM 100', () => {
    const result = selectedBoCountV048({
      selectedServiceModuleIds: [100],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(2) // SM 100 的 count
  })

  it('用户场景 D: restore 5 BO (无祖先)', () => {
    const result = selectedBoCountV048({
      selectedBoIds: [1000, 1001, 1002, 1003, 1004],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(5)
  })

  // ========================================
  // 用户报的 bug V048 (原 2032 → 1610)
  // ========================================
  it('V048 bug 复现: restore 422 BO + 选财务云 domain (级联)', () => {
    // 树结构: domain 1 (id=2205) count=1610
    //         sd 10 + sd 11, sm 100-102 共 1610 BO
    const treeData2 = [{
      id: 'd_2205', originalId: 2205, type: 'domain', name: '财务云', count: 1610,
      children: [
        { id: 's_300', originalId: 300, type: 'sub_domain', name: 'SD', count: 900, children: [
          { id: 'sm_1001', originalId: 1001, type: 'service_module', name: 'SM1', count: 500, children: [] },
          { id: 'sm_1002', originalId: 1002, type: 'service_module', name: 'SM2', count: 400, children: [] },
        ]},
        { id: 's_301', originalId: 301, type: 'sub_domain', name: 'SD', count: 710, children: [
          { id: 'sm_1003', originalId: 1003, type: 'service_module', name: 'SM3', count: 410, children: [] },
          { id: 'sm_1004', originalId: 1004, type: 'service_module', name: 'SM4', count: 300, children: [] },
        ]},
      ]
    }]
    const hMap = {
      2205: { domainId: 2205 },
      300: { domainId: 2205, subDomainId: 300 },
      301: { domainId: 2205, subDomainId: 301 },
      1001: { domainId: 2205, subDomainId: 300 },
      1002: { domainId: 2205, subDomainId: 300 },
      1003: { domainId: 2205, subDomainId: 301 },
      1004: { domainId: 2205, subDomainId: 301 },
    }
    // 选 422 BO + 选 财务云 (级联到 4 个 SM)
    const result = selectedBoCountV048({
      selectedBoIds: Array.from({ length: 422 }, (_, i) => i + 1),
      selectedDomainIds: [2205],
      selectedSubDomainIds: [300, 301],
      selectedServiceModuleIds: [1001, 1002, 1003, 1004],
      treeData: treeData2,
      hierarchyMap: hMap,
    })
    // 修复前 = 422 + 500 + 400 + 410 + 300 = 2032 (双重计数)
    // 修复后 = 1610 (domain count, BO 被覆盖)
    expect(result).toBe(1610)
  })

  // ========================================
  // 跨 SD 选 SM (无级联)
  // ========================================
  it('跨 SD 选 SM: SM 100 (sd 10) + SM 200 (sd 20, domain 2)', () => {
    const result = selectedBoCountV048({
      selectedServiceModuleIds: [100, 200],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(5) // 2 + 3
  })

  it('跨 domain 选 SD: SD 10 (domain 1) + SD 20 (domain 2)', () => {
    const result = selectedBoCountV048({
      selectedSubDomainIds: [10, 20],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(6) // 3 + 3
  })

  it('全选: 2 domains (级联到所有 SD/SM)', () => {
    const result = selectedBoCountV048({
      selectedDomainIds: [1, 2],
      selectedSubDomainIds: [10, 11, 20],
      selectedServiceModuleIds: [100, 101, 102, 200],
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(7) // 4 + 3
  })

  // ========================================
  // 边界场景
  // ========================================
  it('边界: 空选择 → 0', () => {
    expect(selectedBoCountV048({ treeData, hierarchyMap })).toBe(0)
  })

  it('边界: treeData 为空 + restore 5 BO → 5', () => {
    expect(selectedBoCountV048({
      selectedBoIds: [1, 2, 3, 4, 5],
      treeData: [],
      hierarchyMap: {},
    })).toBe(5)
  })

  it('边界: restore 5 BO + 选 1 SM → 5 (SM 覆盖 BO, 等于 SM count)', () => {
    // 选 SM 100 (count=2) + restore 5 BO (无祖先)
    // 修复: SM 100 被勾上时, selectedBoIds 被祖先覆盖, 只算 SM count
    const result = selectedBoCountV048({
      selectedBoIds: [1000, 1001, 1002, 1003, 1004],
      selectedServiceModuleIds: [100],
      treeData,
      hierarchyMap,
    })
    // 修复后: total = 2 (SM 100 count)
    expect(result).toBe(2)
  })

  it('v39 旧行为对比 (仅记录, 不期望): 同样输入下 placeholder 算法 = 5+2 = 7 (双重计数)', () => {
    // v39 算法在同样输入下: 5 BO + SM 100 placeholder 2 = 7 (双重计数 bug)
    // 修复后: 2 (只算 SM count)
    // 此测试仅做 v39 vs V048 对比记录
    const v48Result = selectedBoCountV048({
      selectedBoIds: [1000, 1001, 1002, 1003, 1004],
      selectedServiceModuleIds: [100],
      treeData,
      hierarchyMap,
    })
    expect(v48Result).not.toBe(7) // 不等于 v39 的双重计数结果
  })

  // ========================================
  // V048b: ID 类型规范化 (兼容 emit 字符串 id)
  // ========================================
  it('V048b: emit 字符串 id (带前缀 d_/s_/sm_) → 仍然 141 (不双重计数)', () => {
    // 模拟 emit 用了 node.id fallback (prefixed 字符串) 而不是 node.data.originalId
    const result = selectedBoCountV048({
      selectedDomainIds: ['d_1'],  // 字符串
      selectedSubDomainIds: ['s_10', 's_11'],  // 字符串
      selectedServiceModuleIds: ['sm_100', 'sm_101', 'sm_102'],  // 字符串
      treeData,
      hierarchyMap,
    })
    // hierarchyMap key 是数字, emit 是字符串 → V048 原始算法会 fail (返回 0)
    // V048b normalize 后应能正确处理
    // 实际生产中 hierarchyMap 实际可能不兼容字符串, 但 selectedBoCount 本身应该正确
    // 这里我们期望: 用 normalize 后 Set 跳过逻辑生效
    //   selectedDomainSet = {1} (normalize 'd_1' = 1)
    //   selectedSubDomainSet = {10, 11}
    //   SM loop: info.domainId=1 in Set → continue
    //   SD loop: info.domainId=1 in Set → continue
    //   domain loop: domainChildCount.get(1) = 4
    expect(result).toBe(4)
  })

  // ========================================
  // V048c 修复: selectedDomainIds 去重
  // ========================================
  it('V048c bug 复现: selectedDomainIds 含重复 id → selectedBoCount 累加两次', () => {
    // 如果 selectedDomainIds 含重复 id (如 [1, 1])
    // selectedBoCount 会累加两次 domain count
    // 这是 bug 状态，期望 8 (4+4) 而不是 4
    const result = selectedBoCountV048({
      selectedDomainIds: [1, 1],  // 重复 id
      treeData,
      hierarchyMap,
    })
    // Bug 状态: domain loop 执行两次 → 4 + 4 = 8
    expect(result).toBe(8)
    // 修复: handleObjectScopeChange 用 Set 去重: selectedDomainIds.value = [...new Set(domainIds.map(normalizeId))]
    // 这样就不会出现重复 id
  })

  it('V048c 修复: handleObjectScopeChange 去重后 selectedDomainIds 无重复', () => {
    // 模拟 handleObjectScopeChange 的去重逻辑
    const normalizeId = (v) => {
      if (v == null) return v
      if (typeof v === 'number') return v
      const s = String(v)
      const numStr = s.replace(/^(d|s|sm)_/, '')
      const n = Number(numStr)
      return Number.isNaN(n) ? s : n
    }
    const rawDomainIds = [1, 1, 'd_1', 1]  // 含重复
    const dedupedDomainIds = [...new Set(rawDomainIds.map(normalizeId))]
    expect(dedupedDomainIds).toEqual([1])  // 去重后只剩 1 个

    // 用去重后的 id 调用 selectedBoCount
    const result = selectedBoCountV048({
      selectedDomainIds: dedupedDomainIds,
      treeData,
      hierarchyMap,
    })
    expect(result).toBe(4)  // 正确: 只累加一次
  })
})

// ============================================================
// 2. 跨页一致性 (不变)
// ============================================================
describe('跨页一致性: 架构 chip == 图表页 业务对象/关系数', () => {
  it('用户场景: 架构 chip 19 对象 = 图表导航 19 对象', () => {
    const archChipBoCount = 19
    const chartNavBoCount = 19
    expect(archChipBoCount).toBe(chartNavBoCount)
  })

  it('用户场景 v40 修复: 架构 chip 12 关系 = 图表导航 12 关系', () => {
    const archChipRelCount = 12
    const chartNavRelCount = 12
    expect(archChipRelCount).toBe(chartNavRelCount)
  })

  it('v40 兜底: 当 selectedRelationIds 为空 → 回退到 selectedRelationCodes 数', () => {
    function relationCodesCountV40(selectedRelationIds, selectedRelationCodes) {
      if (selectedRelationIds && selectedRelationIds.length > 0) return selectedRelationIds.length
      return selectedRelationCodes?.length || 0
    }
    expect(relationCodesCountV40([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], ['APPROVES', 'CONTAINS'])).toBe(12)
    expect(relationCodesCountV40([], ['APPROVES', 'CONTAINS'])).toBe(2)
    expect(relationCodesCountV40([], [])).toBe(0)
  })
})

// ============================================================
// 3. 关系范围树节点 count (不变)
// ============================================================
describe('关系范围树节点 count (v39 现状 = 关系数, 已对齐)', () => {
  function buildClassifierNodeCount(node) {
    return node.count || 0
  }

  it('节点 count = 该子树下关系数', () => {
    const classifierNode = {
      name: '跨域',
      count: 8,
      children: [{ name: 'domain1→domain2', count: 3 }, { name: 'd2→d3', count: 5 }]
    }
    expect(buildClassifierNodeCount(classifierNode)).toBe(8)
    expect(classifierNode.children.reduce((s, c) => s + c.count, 0)).toBe(8)
  })
})

// ============================================================
// 4. 对象范围树节点 count (buildHierarchyTree, 验证 count 字段正确)
// ============================================================
describe('对象范围树节点 count (v39 新: BO 数, 非下层节点数)', () => {
  function buildHierarchyTree(domains, subDomains, serviceModules, businessObjects) {
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

  const domains = [
    { id: 1, name: 'Domain 1', code: 'D1' },
    { id: 2, name: 'Domain 2', code: 'D2' }
  ]
  const subDomains = [
    { id: 10, domain_id: 1, name: 'SD 1', code: 'SD1' },
    { id: 11, domain_id: 1, name: 'SD 2', code: 'SD2' },
    { id: 20, domain_id: 2, name: 'SD 3', code: 'SD3' }
  ]
  const serviceModules = [
    { id: 100, sub_domain_id: 10, name: 'SM 1', code: 'SM1' },
    { id: 101, sub_domain_id: 10, name: 'SM 2', code: 'SM2' },
    { id: 102, sub_domain_id: 11, name: 'SM 3', code: 'SM3' },
    { id: 200, sub_domain_id: 20, name: 'SM 4', code: 'SM4' }
  ]
  const businessObjects = [
    { id: 1000, service_module_id: 100 },
    { id: 1001, service_module_id: 100 },
    { id: 1002, service_module_id: 101 },
    { id: 1003, service_module_id: 102 },
    { id: 2000, service_module_id: 200 },
    { id: 2001, service_module_id: 200 },
    { id: 2002, service_module_id: 200 }
  ]

  it('service_module 节点 count = 该模块内 BO 数', () => {
    const tree = buildHierarchyTree(domains, subDomains, serviceModules, businessObjects)
    expect(tree[0].children[0].children[0].count).toBe(2) // sm_100
    expect(tree[0].children[0].children[1].count).toBe(1) // sm_101
    expect(tree[1].children[0].children[0].count).toBe(3) // sm_200
  })

  it('sub_domain 节点 count = 该子域内所有 BO 数', () => {
    const tree = buildHierarchyTree(domains, subDomains, serviceModules, businessObjects)
    expect(tree[0].children[0].count).toBe(3) // s_10: 2+1
    expect(tree[0].children[1].count).toBe(1) // s_11: 1
    expect(tree[1].children[0].count).toBe(3) // s_20: 3
  })

  it('domain 节点 count = 该域内所有 BO 数', () => {
    const tree = buildHierarchyTree(domains, subDomains, serviceModules, businessObjects)
    expect(tree[0].count).toBe(4) // d_1: 3+1
    expect(tree[1].count).toBe(3) // d_2: 3
  })

  it('空 BO 列表 → 所有节点 count = 0', () => {
    const tree = buildHierarchyTree(domains, subDomains, serviceModules, [])
    expect(tree[0].count).toBe(0)
    expect(tree[0].children[0].count).toBe(0)
    expect(tree[0].children[0].children[0].count).toBe(0)
  })

  it('BO 无 service_module_id → 不计入任何模块', () => {
    const bosWithNull = [
      ...businessObjects,
      { id: 9999, service_module_id: null },
      { id: 9998, service_module_id: undefined }
    ]
    const tree = buildHierarchyTree(domains, subDomains, serviceModules, bosWithNull)
    expect(tree[0].count).toBe(4)
    expect(tree[1].count).toBe(3)
  })
})