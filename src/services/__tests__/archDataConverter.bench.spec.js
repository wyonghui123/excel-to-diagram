/**
 * archDataConverter 性能基准测试
 *
 * 目的: 量化 buildPreviewDataFromArchData 的 O(n²) 瓶颈
 * 数据规模: 100 SD + 1000 SM + 10000 BO + 50000 relations
 */
import { describe, it, expect } from 'vitest'
// 注: 故意不 import archDataConverter (避免 vite import-analysis 解析 httpClient.js)
// 改用直接调用: 验证修复后 src/services/archDataConverter.js 的等价逻辑

// 模拟 API 返回: 大数据集
function makeMockApi(dataSize = 'medium') {
  const sizeMap = {
    small: { domains: 5, subDomains: 20, serviceModules: 100, businessObjects: 500, relationships: 1000 },
    medium: { domains: 10, subDomains: 50, serviceModules: 500, businessObjects: 5000, relationships: 10000 },
    large: { domains: 20, subDomains: 100, serviceModules: 1000, businessObjects: 10000, relationships: 50000 }
  }
  const size = sizeMap[dataSize]

  const domains = Array.from({ length: size.domains }, (_, i) => ({ id: i + 1, name: `Domain${i}`, code: `D${i}` }))
  const subDomains = []
  const serviceModules = []
  const businessObjects = []
  const relationships = []

  let smId = 1, boId = 1, relId = 1
  for (const domain of domains) {
    for (let sd = 0; sd < Math.ceil(size.subDomains / size.domains); sd++) {
      if (subDomains.length >= size.subDomains) break
      const sdId = subDomains.length + 1
      subDomains.push({
        id: sdId, domain_id: domain.id, name: `SubDomain${sdId}`, code: `SD${sdId}`,
        domain_name: domain.name
      })
      for (let sm = 0; sm < Math.ceil(size.serviceModules / size.subDomains); sm++) {
        if (serviceModules.length >= size.serviceModules) break
        const smRow = {
          id: smId, sub_domain_id: sdId, name: `SM${smId}`, code: `SM${smId}`,
          sub_domain_name: `SubDomain${sdId}`, domain_name: domain.name
        }
        serviceModules.push(smRow)
        for (let bo = 0; bo < Math.ceil(size.businessObjects / size.serviceModules); bo++) {
          if (businessObjects.length >= size.businessObjects) break
          businessObjects.push({
            id: boId, code: `BO${boId}`, name: `BO${boId}`,
            service_module_id: smId, service_module_name: `SM${smId}`,
            sub_domain_id: sdId, sub_domain_name: `SubDomain${sdId}`,
            domain_id: domain.id, domain_name: domain.name
          })
          boId++
        }
        smId++
      }
    }
  }

  for (let i = 0; i < size.relationships; i++) {
    const srcIdx = i % businessObjects.length
    const tgtIdx = (i * 7 + 3) % businessObjects.length
    relationships.push({
      id: relId++, relation_type: 'depends', relation_type_name: '依赖',
      relation_code: `REL_${i}`, source_code: businessObjects[srcIdx].code, target_code: businessObjects[tgtIdx].code,
      relation_desc: '', scope_type: 'internal', category_type: 'cross-domain'
    })
  }

  return {
    domains, sub_domains: subDomains, service_modules: serviceModules,
    business_objects: businessObjects, relationships,
    center_scope: businessObjects.slice(0, 50).map(b => b.code)
  }
}

describe('archDataConverter 性能基准', () => {
  it('small (100 SM, 500 BO, 1000 rel) - 测量 buildPreviewDataFromArchData', () => {
    const mockData = makeMockApi('small')
    const start = performance.now()

    const smBuildStart = performance.now()
    const smResult = mockData.service_modules.map(sm => {
      const smBOs = mockData.business_objects.filter(bo => bo.service_module_id === sm.id)
      return { id: sm.id, name: sm.name, code: sm.code, businessObjects: smBOs.map(b => b.code) }
    })
    const smBuildTime = performance.now() - smBuildStart

    const totalTime = performance.now() - start
    console.log(`[BENCH-small] buildServiceModules: ${smBuildTime.toFixed(2)}ms (100 SM x 500 BO)`)
    console.log(`[BENCH-small] total: ${totalTime.toFixed(2)}ms`)

    expect(smResult.length).toBe(100)
  })

  it('medium (500 SM, 5000 BO, 10000 rel) - 验证 O(n²) 恶化', () => {
    const mockData = makeMockApi('medium')

    const start1 = performance.now()
    const smResultCurrent = mockData.service_modules.map(sm => {
      const smBOs = mockData.business_objects.filter(bo => bo.service_module_id === sm.id)
      return { id: sm.id, businessObjects: smBOs.map(b => b.code) }
    })
    const t1 = performance.now() - start1

    const start2 = performance.now()
    const boBySm = new Map()
    for (const bo of mockData.business_objects) {
      if (!boBySm.has(bo.service_module_id)) boBySm.set(bo.service_module_id, [])
      boBySm.get(bo.service_module_id).push(bo)
    }
    const smResultOpt = mockData.service_modules.map(sm => {
      const smBOs = boBySm.get(sm.id) || []
      return { id: sm.id, businessObjects: smBOs.map(b => b.code) }
    })
    const t2 = performance.now() - start2

    console.log(`[BENCH-medium] current (O(n^2)): ${t1.toFixed(2)}ms`)
    console.log(`[BENCH-medium] optimized (O(n)): ${t2.toFixed(2)}ms`)
    console.log(`[BENCH-medium] speedup: ${(t1 / t2).toFixed(1)}x`)

    expect(smResultCurrent.length).toBe(smResultOpt.length)
  })

  it('large (1000 SM, 10000 BO, 50000 rel) - 真实用户场景', () => {
    const mockData = makeMockApi('large')

    const start1 = performance.now()
    const smResultCurrent = mockData.service_modules.map(sm => {
      const smBOs = mockData.business_objects.filter(bo => bo.service_module_id === sm.id)
      return { id: sm.id, businessObjects: smBOs.map(b => b.code) }
    })
    const t1 = performance.now() - start1

    const start2 = performance.now()
    const boBySm = new Map()
    for (const bo of mockData.business_objects) {
      if (!boBySm.has(bo.service_module_id)) boBySm.set(bo.service_module_id, [])
      boBySm.get(bo.service_module_id).push(bo)
    }
    const smResultOpt = mockData.service_modules.map(sm => {
      const smBOs = boBySm.get(sm.id) || []
      return { id: sm.id, businessObjects: smBOs.map(b => b.code) }
    })
    const t2 = performance.now() - start2

    console.log(`[BENCH-large] current (O(n^2)): ${t1.toFixed(2)}ms (1000 SM x 10000 BO)`)
    console.log(`[BENCH-large] optimized (O(n)): ${t2.toFixed(2)}ms`)
    console.log(`[BENCH-large] speedup: ${(t1 / t2).toFixed(1)}x`)

    if (t1 / t2 > 5) {
      console.log(`[BENCH-large] HIGH-VALUE OPTIMIZATION: ${(t1 / t2).toFixed(1)}x speedup achievable`)
    }
  })

  it('relationships filter 优化: 关系 x BO 查找 用 Map 替代 filter', () => {
    const mockData = makeMockApi('large')
    const filteredBOs = mockData.business_objects.slice(0, 5000)

    const start1 = performance.now()
    let count1 = 0
    for (const rel of mockData.relationships) {
      const src = filteredBOs.find(bo => bo.code === rel.source_code)
      const tgt = filteredBOs.find(bo => bo.code === rel.target_code)
      if (src && tgt) count1++
    }
    const t1 = performance.now() - start1

    const start2 = performance.now()
    const boByCode = new Map()
    for (const bo of filteredBOs) boByCode.set(bo.code, bo)
    let count2 = 0
    for (const rel of mockData.relationships) {
      const src = boByCode.get(rel.source_code)
      const tgt = boByCode.get(rel.target_code)
      if (src && tgt) count2++
    }
    const t2 = performance.now() - start2

    console.log(`[BENCH-rels] current: ${t1.toFixed(2)}ms, optimized: ${t2.toFixed(2)}ms, speedup: ${(t1 / t2).toFixed(1)}x`)
    expect(count1).toBe(count2)
  })
})

describe('修复方案: 最小 O(n^2) 优化 (不改业务逻辑)', () => {
  it('[FIX-PLAN-1] buildServiceModules: O(n^2) → O(n) 预建 Map 优化', () => {
    const mockData = makeMockApi('large')
    const { service_modules, business_objects } = mockData

    const t1 = performance.now()
    const current = service_modules.map(sm => {
      const smBOs = business_objects.filter(bo => bo.service_module_id === sm.id)
      return { id: sm.id, name: sm.name, code: sm.code, businessObjects: smBOs.map(b => b.code) }
    })
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const boBySm = new Map()
    for (const bo of business_objects) {
      if (!boBySm.has(bo.service_module_id)) boBySm.set(bo.service_module_id, [])
      boBySm.get(bo.service_module_id).push(bo)
    }
    const optimized = service_modules.map(sm => {
      const smBOs = boBySm.get(sm.id) || []
      return { id: sm.id, name: sm.name, code: sm.code, businessObjects: smBOs.map(b => b.code) }
    })
    const tOpt = performance.now() - t2

    expect(optimized.length).toBe(current.length)
    for (let i = 0; i < current.length; i++) {
      expect(optimized[i].businessObjects).toEqual(current[i].businessObjects)
    }
    console.log(`[FIX-PLAN-1] 优化: ${tCurrent.toFixed(2)}ms → ${tOpt.toFixed(2)}ms (${(tCurrent / tOpt).toFixed(1)}x)`)
  })

  it('[FIX-PLAN-2] internalRelationFilter: O(rels x bos) → O(rels + bos) 优化', () => {
    const mockData = makeMockApi('large')
    const filteredBOs = mockData.business_objects.slice(0, 5000)

    const t1 = performance.now()
    const current = mockData.relationships.filter(rel => {
      const sourceBo = filteredBOs.find(bo => bo.code === rel.source_code)
      const targetBo = filteredBOs.find(bo => bo.code === rel.target_code)
      return sourceBo && targetBo
    })
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const boByCode = new Map()
    for (const bo of filteredBOs) boByCode.set(bo.code, bo)
    const optimized = mockData.relationships.filter(rel => {
      const sourceBo = boByCode.get(rel.source_code)
      const targetBo = boByCode.get(rel.target_code)
      return sourceBo && targetBo
    })
    const tOpt = performance.now() - t2

    expect(optimized.length).toBe(current.length)
    console.log(`[FIX-PLAN-2] 优化: ${tCurrent.toFixed(2)}ms → ${tOpt.toFixed(2)}ms (${(tCurrent / tOpt).toFixed(1)}x)`)
  })
})

describe('深入分析: useDiagramData.js 其他高风险 O(n^2) 热点', () => {
  it('[DEEP-1] filteredDomainProducts 三层嵌套 find 性能 + 优化方案', () => {
    const filteredDomainProducts = []
    for (let d = 0; d < 50; d++) {
      const modules = []
      for (let sd = 0; sd < 100; sd++) {
        const submodules = []
        for (let sm = 0; sm < 100; sm++) {
          submodules.push({ code: `sm-${d}-${sd}-${sm}`, name: `sm-${sm}`, isCenter: false })
        }
        modules.push({ name: `sd-${d}-${sd}`, isCenter: false, submodules })
      }
      filteredDomainProducts.push({ name: `domain-${d}`, isCenter: false, modules })
    }
    const orphanSms = Array.from({ length: 1000 }, (_, i) => `orphan-sm-${i}`)

    const t1 = performance.now()
    let countCurrent = 0
    for (const smCode of orphanSms) {
      const domainName = `domain-${smCode.length % 50}`
      const subDomainName = `sd-${(smCode.length * 3) % 100}`
      const domainEntry = filteredDomainProducts.find(d => d.name === domainName)
      if (domainEntry) {
        const sdEntry = domainEntry.modules.find(sd => sd.name === subDomainName)
        if (sdEntry) {
          const smEntry = sdEntry.submodules.find(sm => sm.code === smCode)
          if (smEntry) countCurrent++
        }
      }
    }
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const domainByName = new Map()
    const sdByKey = new Map()
    const smByCode = new Map()
    for (const d of filteredDomainProducts) {
      domainByName.set(d.name, d)
      for (const sd of d.modules) {
        sdByKey.set(`${d.name}::${sd.name}`, sd)
        for (const sm of sd.submodules) {
          smByCode.set(sm.code, sm)
        }
      }
    }
    let countOpt = 0
    for (const smCode of orphanSms) {
      const domainName = `domain-${smCode.length % 50}`
      const subDomainName = `sd-${(smCode.length * 3) % 100}`
      const domainEntry = domainByName.get(domainName)
      if (domainEntry) {
        const sdEntry = sdByKey.get(`${domainName}::${subDomainName}`)
        if (sdEntry) {
          const smEntry = smByCode.get(smCode)
          if (smEntry) countOpt++
        }
      }
    }
    const tOpt = performance.now() - t2

    console.log(`[DEEP-1] 三层 .find(): ${tCurrent.toFixed(2)}ms (1000 orphan x 250 比较)`)
    console.log(`[DEEP-1] 预建 Map: ${tOpt.toFixed(2)}ms`)
    console.log(`[DEEP-1] speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
    expect(countOpt).toBe(countCurrent)
  })

  it('[DEEP-2] filteredBusinessObjects.filter 在 orphan 循环内调用 性能 + 优化', () => {
    const filteredBusinessObjects = []
    for (let i = 0; i < 10000; i++) {
      filteredBusinessObjects.push({
        code: `BO${i}`, serviceModule: `SM${i % 1000}`,
        domain: `D${i % 20}`, subDomain: `SD${i % 100}`, serviceModuleName: `SM Name ${i % 1000}`
      })
    }
    const orphanSms = Array.from({ length: 1000 }, (_, i) => `SM${i}`)

    const t1 = performance.now()
    for (const smCode of orphanSms) {
      const smBos = filteredBusinessObjects.filter(bo => bo.serviceModule === smCode)
      if (smBos.length > 0) {
        const domainName = smBos[0].domain
      }
    }
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const boBySm = new Map()
    for (const bo of filteredBusinessObjects) {
      if (!boBySm.has(bo.serviceModule)) boBySm.set(bo.serviceModule, [])
      boBySm.get(bo.serviceModule).push(bo)
    }
    for (const smCode of orphanSms) {
      const smBos = boBySm.get(smCode) || []
      if (smBos.length > 0) {
        const domainName = smBos[0].domain
      }
    }
    const tOpt = performance.now() - t2

    console.log(`[DEEP-2] orphan .filter: ${tCurrent.toFixed(2)}ms (1000 x 10000 BO)`)
    console.log(`[DEEP-2] boBySm Map: ${tOpt.toFixed(2)}ms`)
    console.log(`[DEEP-2] speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })

  it('[DEEP-3] validateData 性能: 5000 rels x 2 bo check', () => {
    const data = {
      businessObjects: Array.from({ length: 1000 }, (_, i) => ({
        code: `BO${i}`, name: `BO${i}`,
        domain: `D1`, subDomain: `SD1`, serviceModule: `SM${i % 100}`
      })),
      relationships: Array.from({ length: 5000 }, (_, i) => ({
        id: i, sourceCode: `BO${i % 1000}`, targetCode: `BO${(i * 7) % 1000}`,
        relationCode: `REL${i}`
      }))
    }

    const boSet = new Set(data.businessObjects.map(b => b.code))
    const t1 = performance.now()
    let invalidCount = 0
    for (const rel of data.relationships) {
      if (!boSet.has(rel.sourceCode) || !boSet.has(rel.targetCode)) {
        invalidCount++
      }
    }
    const tCurrent = performance.now() - t1

    console.log(`[DEEP-3] validateData: ${tCurrent.toFixed(2)}ms (5000 rels x 2 bo Set has)`)
    console.log(`[DEEP-3] invalid rels: ${invalidCount}`)
  })

  it('[DEEP-4] 综合优化: orphan SM 补齐全链路 (3 个 O(n^2) 修复)', () => {
    const filteredDomainProducts = []
    for (let d = 0; d < 50; d++) {
      const modules = []
      for (let sd = 0; sd < 4; sd++) {
        const submodules = []
        for (let sm = 0; sm < 5; sm++) {
          submodules.push({ code: `sm-${d}-${sd}-${sm}`, isCenter: false })
        }
        modules.push({ name: `sd-${d}-${sd}`, submodules })
      }
      filteredDomainProducts.push({ name: `domain-${d}`, modules })
    }
    const filteredBusinessObjects = []
    for (let i = 0; i < 10000; i++) {
      filteredBusinessObjects.push({
        code: `BO${i}`, serviceModule: `orphan-sm-${i % 500}`,
        domain: `D${i % 20}`, subDomain: `SD${i % 50}`, serviceModuleName: `SM Name ${i % 500}`
      })
    }
    const filteredSmCodes = new Set(Array.from({ length: 500 }, (_, i) => `orphan-sm-${i}`))

    const t1 = performance.now()
    const placedSmCodes = new Set()
    filteredDomainProducts.forEach(domain => {
      domain.modules?.forEach(sd => sd.submodules?.forEach(sm => placedSmCodes.add(sm.code)))
    })
    filteredSmCodes.forEach(smCode => {
      if (!placedSmCodes.has(smCode)) {
        const smBos = filteredBusinessObjects.filter(bo => bo.serviceModule === smCode)
        if (smBos.length > 0) {
          const domainName = smBos[0].domain || '其他领域'
          const subDomainName = smBos[0].subDomain || '其他子领域'
          let domainEntry = filteredDomainProducts.find(d => d.name === domainName)
          if (!domainEntry) {
            domainEntry = { name: domainName, isCenter: false, modules: [] }
            filteredDomainProducts.push(domainEntry)
          }
          domainEntry.modules.find(sd => sd.name === subDomainName)
        }
      }
    })
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const boBySm = new Map()
    for (const bo of filteredBusinessObjects) {
      if (!boBySm.has(bo.serviceModule)) boBySm.set(bo.serviceModule, [])
      boBySm.get(bo.serviceModule).push(bo)
    }
    const domainByName = new Map()
    const sdByKey = new Map()
    for (const d of filteredDomainProducts) {
      domainByName.set(d.name, d)
      for (const sd of d.modules) {
        sdByKey.set(`${d.name}::${sd.name}`, sd)
      }
    }
    filteredSmCodes.forEach(smCode => {
      const smBos = boBySm.get(smCode) || []
      if (smBos.length > 0) {
        const domainName = smBos[0].domain || '其他领域'
        const subDomainName = smBos[0].subDomain || '其他子领域'
        let domainEntry = domainByName.get(domainName)
        if (!domainEntry) {
          domainEntry = { name: domainName, isCenter: false, modules: [] }
          filteredDomainProducts.push(domainEntry)
          domainByName.set(domainName, domainEntry)
        }
        sdByKey.get(`${domainName}::${subDomainName}`)
      }
    })
    const tOpt = performance.now() - t2

    console.log(`[DEEP-4] orphan SM 全链路: ${tCurrent.toFixed(2)}ms (当前)`)
    console.log(`[DEEP-4] orphan SM 全链路: ${tOpt.toFixed(2)}ms (3 个 Map 优化)`)
    console.log(`[DEEP-4] speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})
