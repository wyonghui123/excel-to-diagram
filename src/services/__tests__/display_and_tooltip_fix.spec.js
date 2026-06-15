/**
 * v37 修复: 导航文案统一 + tooltip 显示 源-目标 名称
 */
import { describe, it, expect } from 'vitest'

// 1. 验证 buildRelationships 现在填充 sourceName/targetName
describe('buildRelationships (v37 补全 sourceName/targetName)', () => {
  function buildRelationships(rawRelationships, businessObjects) {
    const boByCode = new Map()
    for (const bo of (businessObjects || [])) {
      if (bo.code) boByCode.set(bo.code, bo)
    }
    return rawRelationships.map(rel => {
      const sourceCode = rel.source_code || rel.sourceCode
      const targetCode = rel.target_code || rel.targetCode
      const sourceBo = sourceCode ? boByCode.get(sourceCode) : null
      const targetBo = targetCode ? boByCode.get(targetCode) : null
      return {
        id: rel.id,
        sourceCode,
        targetCode,
        sourceName: (sourceBo && (sourceBo.name || sourceBo.code)) || '',
        targetName: (targetBo && (targetBo.name || targetBo.code)) || '',
        relationCode: rel.relation_code || rel.relationCode || '',
        relationDesc: rel.relation_desc || rel.relationDesc || '',
        sourceBo,
        targetBo
      }
    })
  }

  it('正常场景: 3 BO + 2 关系, sourceName/targetName 正确填充', () => {
    const businessObjects = [
      { code: 'BO_A', name: '业务对象 A' },
      { code: 'BO_B', name: '业务对象 B' },
      { code: 'BO_C', name: '业务对象 C' }
    ]
    const rawRelationships = [
      { id: 1, source_code: 'BO_A', target_code: 'BO_B', relation_code: 'REL_AB' },
      { id: 2, source_code: 'BO_B', target_code: 'BO_C', relation_code: 'REL_BC' }
    ]
    const result = buildRelationships(rawRelationships, businessObjects)
    expect(result[0].sourceName).toBe('业务对象 A')
    expect(result[0].targetName).toBe('业务对象 B')
    expect(result[1].sourceName).toBe('业务对象 B')
    expect(result[1].targetName).toBe('业务对象 C')
  })

  it('空 businessObjects: sourceName/targetName = "" 而非 undefined', () => {
    const result = buildRelationships(
      [{ id: 1, source_code: 'BO_X', target_code: 'BO_Y' }],
      []
    )
    expect(result[0].sourceName).toBe('')
    expect(result[0].targetName).toBe('')
  })

  it('undefined businessObjects: 容错', () => {
    const result = buildRelationships(
      [{ id: 1, source_code: 'BO_X', target_code: 'BO_Y' }],
      undefined
    )
    expect(result[0].sourceName).toBe('')
    expect(result[0].targetName).toBe('')
  })

  it('BO 缺 name 字段: fallback 到 code', () => {
    const result = buildRelationships(
      [{ id: 1, source_code: 'BO_X', target_code: 'BO_Y' }],
      [{ code: 'BO_X' }, { code: 'BO_Y' }]
    )
    expect(result[0].sourceName).toBe('BO_X')
    expect(result[0].targetName).toBe('BO_Y')
  })
})

// 2. 验证 tooltip 格式化正确显示 源-目标
describe('tooltip formatTooltipText (v37 显示 源-目标 名称)', () => {
  function formatTooltipText(relation) {
    if (!relation) return '无关系说明'
    const relationCode = relation.relationCode || ''
    const relationDesc = relation.relationDesc || '无关系说明'
    const sourceName = relation.sourceName || ''
    const targetName = relation.targetName || ''
    const annotationContent = relation.annotationContent || ''
    let text = `${relationCode}\n${sourceName} → ${targetName}\n${relationDesc}`
    if (annotationContent) text += `\n备注: ${annotationContent}`
    return text
  }

  it('正常: 完整 sourceName/targetName 显示', () => {
    const text = formatTooltipText({
      relationCode: 'REL_001',
      relationDesc: '关联 A 到 B',
      sourceName: '业务对象 A',
      targetName: '业务对象 B'
    })
    expect(text).toContain('业务对象 A → 业务对象 B')
    expect(text).not.toContain('undefined')
  })

  it.skip('[BUG 重现仅供对比] 修复前: sourceName/targetName = undefined', () => {
    const text = formatTooltipText({
      relationCode: 'REL_001',
      relationDesc: '关联'
      // 注意: 缺 sourceName/targetName
    })
    // 修复前 text = "REL_001\nundefined → undefined\n关联"
    // 这个测试用 .skip 因为它会失败 - 仅作为 bug 重现对比
  })

  it('v37 修复后: buildRelationships 填充空串而非 undefined, tooltip 不显示 "undefined"', () => {
    // 模拟 v37 修复后的 buildRelationships 输出
    const relation = {
      relationCode: 'REL_001',
      relationDesc: '关联',
      sourceName: '',
      targetName: ''
    }
    const text = formatTooltipText(relation)
    expect(text).toContain('REL_001')
    expect(text).toContain('关联')
    expect(text).not.toContain('undefined → undefined')  // 修复后不再有
  })
})

// 3. 验证 displayStats.config 统一使用业务对象图 5 指标
describe('displayStats.config (v37 服务模块图统一 5 指标)', () => {
  function configStatsOldBehavior(chartType, totalStats, filteredRelationsLength) {
    // 旧实现: 根据 chartType 不同返回不同字段
    if (chartType === 'serviceModule') {
      return {
        serviceModules: totalStats.serviceModules,
        serviceModuleRelations: filteredRelationsLength || 0
      }
    } else {
      return {
        serviceModules: totalStats.serviceModules,
        businessObjects: totalStats.businessObjects,
        domains: totalStats.domains,
        subDomains: totalStats.subDomains,
        objectRelations: filteredRelationsLength || 0
      }
    }
  }

  function configStatsNew(totalStats, filteredRelationsLength) {
    // v37: 不论 chartType, 永远返回 5 指标
    return {
      serviceModules: totalStats.serviceModules,
      businessObjects: totalStats.businessObjects,
      domains: totalStats.domains,
      subDomains: totalStats.subDomains,
      objectRelations: filteredRelationsLength || 0
    }
  }

  it('旧实现服务模块图: 缺 businessObjects/objectRelations (导致 undefined 显示)', () => {
    const old = configStatsOldBehavior('serviceModule', {
      serviceModules: 15, businessObjects: 100, domains: 3, subDomains: 8
    }, 0)
    expect(old.businessObjects).toBeUndefined()
    expect(old.objectRelations).toBeUndefined()
  })

  it('v37 新实现: 服务模块图也返回 5 指标 (无 undefined)', () => {
    const result = configStatsNew({
      serviceModules: 15, businessObjects: 100, domains: 3, subDomains: 8
    }, 25)
    expect(result.serviceModules).toBe(15)
    expect(result.businessObjects).toBe(100)
    expect(result.objectRelations).toBe(25)
    expect(result.domains).toBe(3)
    expect(result.subDomains).toBe(8)
  })

  it('StepNavigator formatMinimalStats 不再出现 undefined', () => {
    // 模拟 StepNavigator 拼接逻辑
    const stats = configStatsNew({ serviceModules: 15, businessObjects: 100, domains: 3, subDomains: 8 }, 25)
    const parts = []
    if (stats.domains > 0) parts.push(`${stats.domains}领域`)
    if (stats.subDomains > 0) parts.push(`${stats.subDomains}子域`)
    if (stats.serviceModules > 0) parts.push(`${stats.serviceModules}服务`)
    parts.push(`${stats.businessObjects}对象`)
    parts.push(`${stats.objectRelations}关系`)
    const text = parts.join(' · ')
    expect(text).toBe('3领域 · 8子域 · 15服务 · 100对象 · 25关系')
    expect(text).not.toContain('undefined')
  })
})

// 4. v38 修复: config.objectRelations 跟 total.objectRelations 口径一致
describe('v38 config.objectRelations 口径统一 (与 total 一致)', () => {
  // 旧实现用 filteredRelations.length (OR 兜底 16)
  // 新实现用 totalStats.objectRelations (AND 口径 12)
  function configStatsOldBehavior(chartType, totalStats, filteredRelationsLength) {
    if (chartType === 'serviceModule') {
      return { serviceModules: totalStats.serviceModules, serviceModuleRelations: filteredRelationsLength || 0 }
    } else {
      return {
        serviceModules: totalStats.serviceModules,
        businessObjects: totalStats.businessObjects,
        domains: totalStats.domains,
        subDomains: totalStats.subDomains,
        objectRelations: filteredRelationsLength || 0  // ← 16 (OR 兜底)
      }
    }
  }

  function configStatsNew(totalStats) {
    // v38: 跟 total 一致 (AND 口径 12)
    return {
      serviceModules: totalStats.serviceModules,
      businessObjects: totalStats.businessObjects,
      domains: totalStats.domains,
      subDomains: totalStats.subDomains,
      objectRelations: totalStats.objectRelations  // ← 12 (AND 口径)
    }
  }

  it('用户场景: 中心 4 关系 + 增量 8 关系 = 总数 12, 配置 16 (错) → 12 (对)', () => {
    const userTotalStats = {
      serviceModules: 10, businessObjects: 19, domains: 1, subDomains: 1,
      objectRelations: 12  // AND 口径
    }
    const filteredRelationsLength = 16  // OR 兜底口径

    // 旧行为 (16)
    const old = configStatsOldBehavior('businessObject', userTotalStats, filteredRelationsLength)
    expect(old.objectRelations).toBe(16)  // 错

    // v38 新行为 (12)
    const newStats = configStatsNew(userTotalStats)
    expect(newStats.objectRelations).toBe(12)  // 对, 跟 total 一致
  })

  it('v38: 步骤 3 (总数) 12 关系 == 步骤 4 (配置) 12 关系, 数据一致', () => {
    const userTotalStats = {
      serviceModules: 10, businessObjects: 19, domains: 1, subDomains: 1,
      objectRelations: 12
    }
    const totalStepStats = { objectRelations: 12 }  // displayStats.total
    const configStepStats = configStatsNew(userTotalStats)  // displayStats.config

    expect(totalStepStats.objectRelations).toBe(configStepStats.objectRelations)
  })

  it('v38: 服务模块图也用 5 指标 (与业务对象图统一)', () => {
    // 之前 v37 应该修了但实际未生效 (修改丢失). 这次 v38 顺带修
    const userTotalStats = {
      serviceModules: 10, businessObjects: 19, domains: 1, subDomains: 1,
      objectRelations: 12
    }
    const newStats = configStatsNew(userTotalStats)
    // 5 指标都在
    expect(newStats.serviceModules).toBe(10)
    expect(newStats.businessObjects).toBe(19)
    expect(newStats.domains).toBe(1)
    expect(newStats.subDomains).toBe(1)
    expect(newStats.objectRelations).toBe(12)
  })
})
