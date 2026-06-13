/**
 * 深入优化 benchmark - 最终轮 (#10-#12)
 */
import { describe, it, expect } from 'vitest'

// #12. filteredDomainProducts computed - 5 处 O(n²+)
describe('useDiagramData.filteredDomainProducts (5 处 O(n^2+))', () => {
  function filteredDomainProductsCurrent(previewData, centerScope, relationFilteredBoCodes) {
    const centerScopeSet = new Set(centerScope || [])
    const relationSet = new Set(relationFilteredBoCodes || [])
    const finalBoCodes = new Set([...centerScopeSet, ...relationSet])
    const hasFilter = finalBoCodes.size > 0

    const filteredDomainProducts = []

    previewData.domainProducts.forEach(domain => {
      const filteredDomain = { name: domain.name, code: domain.code, isCenter: false, modules: [] }
      domain.modules?.forEach(subDomain => {
        const filteredSubDomain = { name: subDomain.name, code: subDomain.code, isCenter: false, submodules: [] }
        subDomain.submodules?.forEach(sm => {
          // [BOTTLENECK-1] some
          const hasAnyBo = previewData.businessObjects.some(bo => bo.serviceModule === sm.code && finalBoCodes.has(bo.code))
          if (!hasFilter || hasAnyBo) {
            // [BOTTLENECK-2] some 再次
            filteredSubDomain.submodules.push({
              ...sm,
              isCenter: hasFilter && centerScopeSet.size > 0
                ? previewData.businessObjects.some(bo => bo.serviceModule === sm.code && centerScopeSet.has(bo.code))
                : false
            })
          }
        })
        if (filteredSubDomain.submodules.length > 0) {
          filteredSubDomain.isCenter = filteredSubDomain.submodules.some(sm => sm.isCenter)
          filteredDomain.modules.push(filteredSubDomain)
        }
      })
      if (filteredDomain.modules.length > 0) {
        filteredDomain.isCenter = filteredDomain.modules.some(m => m.isCenter)
        filteredDomainProducts.push(filteredDomain)
      }
    })

    // [BOTTLENECK-3] 4 层嵌套收集 placedBoCodes
    if (hasFilter) {
      const placedBoCodes = new Set()
      filteredDomainProducts.forEach(domain => {
        domain.modules?.forEach(sd => {
          sd.submodules?.forEach(sm => {
            previewData.businessObjects.forEach(bo => {
              if (bo.serviceModule === sm.code && finalBoCodes.has(bo.code)) {
                placedBoCodes.add(bo.code)
              }
            })
          })
        })
      })

      // [BOTTLENECK-4] 收集 orphan
      const orphanHierarchy = new Map()
      previewData.businessObjects.forEach(bo => {
        if (finalBoCodes.has(bo.code) && !placedBoCodes.has(bo.code)) {
          const domainName = bo.domain
          const subDomainName = bo.subDomain
          const smCode = bo.serviceModule
          if (!orphanHierarchy.has(domainName)) orphanHierarchy.set(domainName, new Map())
          const sdMap = orphanHierarchy.get(domainName)
          if (!sdMap.has(subDomainName)) sdMap.set(subDomainName, new Map())
          const smMap = sdMap.get(subDomainName)
          if (!smMap.has(smCode)) smMap.set(smCode, { name: smCode, codes: [] })
          smMap.get(smCode).codes.push(bo.code)
        }
      })

      // [BOTTLENECK-5] 3 层 find 合并
      orphanHierarchy.forEach((sdMap, domainName) => {
        let domainEntry = filteredDomainProducts.find(d => d.name === domainName)
        if (!domainEntry) {
          domainEntry = { name: domainName, code: domainName, modules: [] }
          filteredDomainProducts.push(domainEntry)
        }
        sdMap.forEach((smMap, subDomainName) => {
          let sdEntry = domainEntry.modules.find(sd => sd.name === subDomainName)
          if (!sdEntry) {
            sdEntry = { name: subDomainName, code: subDomainName, submodules: [] }
            domainEntry.modules.push(sdEntry)
          }
          smMap.forEach((smInfo, smCode) => {
            let smEntry = sdEntry.submodules.find(sm => sm.code === smCode)
            if (!smEntry) {
              smEntry = { name: smInfo.name, code: smCode, isCenter: false, businessObjects: smInfo.codes }
              sdEntry.submodules.push(smEntry)
            }
          })
        })
      })
    }

    return filteredDomainProducts
  }

  function filteredDomainProductsOpt(previewData, centerScope, relationFilteredBoCodes) {
    const centerScopeSet = new Set(centerScope || [])
    const relationSet = new Set(relationFilteredBoCodes || [])
    const finalBoCodes = new Set([...centerScopeSet, ...relationSet])
    const hasFilter = finalBoCodes.size > 0

    // [FIX-PERF] 预建 boBySm 一次, 替代 5 处 O(SM × BO) some/find
    const boBySm = new Map()
    for (const bo of previewData.businessObjects) {
      if (!boBySm.has(bo.serviceModule)) boBySm.set(bo.serviceModule, [])
      boBySm.get(bo.serviceModule).push(bo)
    }

    const filteredDomainProducts = []

    previewData.domainProducts.forEach(domain => {
      const filteredDomain = { name: domain.name, code: domain.code, isCenter: false, modules: [] }
      domain.modules?.forEach(subDomain => {
        const filteredSubDomain = { name: subDomain.name, code: subDomain.code, isCenter: false, submodules: [] }
        subDomain.submodules?.forEach(sm => {
          // [FIX-PERF] 用 boBySm 替代 .some
          const smBos = boBySm.get(sm.code) || []
          let hasAnyBo = false
          for (const bo of smBos) if (finalBoCodes.has(bo.code)) { hasAnyBo = true; break }
          if (!hasFilter || hasAnyBo) {
            // [FIX-PERF] 同样用 boBySm
            let isCenter = false
            if (hasFilter && centerScopeSet.size > 0) {
              for (const bo of smBos) if (centerScopeSet.has(bo.code)) { isCenter = true; break }
            }
            filteredSubDomain.submodules.push({ ...sm, isCenter })
          }
        })
        if (filteredSubDomain.submodules.length > 0) {
          filteredSubDomain.isCenter = filteredSubDomain.submodules.some(sm => sm.isCenter)
          filteredDomain.modules.push(filteredSubDomain)
        }
      })
      if (filteredDomain.modules.length > 0) {
        filteredDomain.isCenter = filteredDomain.modules.some(m => m.isCenter)
        filteredDomainProducts.push(filteredDomain)
      }
    })

    if (hasFilter) {
      // [FIX-PERF] 用 boBySm 替代 4 层嵌套
      const placedBoCodes = new Set()
      for (const domain of filteredDomainProducts) {
        for (const sd of (domain.modules || [])) {
          for (const sm of (sd.submodules || [])) {
            const smBos = boBySm.get(sm.code) || []
            for (const bo of smBos) if (finalBoCodes.has(bo.code)) placedBoCodes.add(bo.code)
          }
        }
      }

      const orphanHierarchy = new Map()
      for (const bo of previewData.businessObjects) {
        if (finalBoCodes.has(bo.code) && !placedBoCodes.has(bo.code)) {
          const domainName = bo.domain
          const subDomainName = bo.subDomain
          const smCode = bo.serviceModule
          if (!orphanHierarchy.has(domainName)) orphanHierarchy.set(domainName, new Map())
          const sdMap = orphanHierarchy.get(domainName)
          if (!sdMap.has(subDomainName)) sdMap.set(subDomainName, new Map())
          const smMap = sdMap.get(subDomainName)
          if (!smMap.has(smCode)) smMap.set(smCode, { name: smCode, codes: [] })
          smMap.get(smCode).codes.push(bo.code)
        }
      }

      // [FIX-PERF] 预建 domainByName / sdByKey / smByCode 替代 3 层 find
      const domainByName = new Map()
      const sdByKey = new Map()
      const smByKey = new Map()
      for (const d of filteredDomainProducts) {
        domainByName.set(d.name, d)
        for (const sd of (d.modules || [])) {
          sdByKey.set(`${d.name}::${sd.name}`, sd)
          for (const sm of (sd.submodules || [])) {
            smByKey.set(`${sd.name}::${sm.code}`, sm)
          }
        }
      }
      for (const [domainName, sdMap] of orphanHierarchy) {
        let domainEntry = domainByName.get(domainName)
        if (!domainEntry) {
          domainEntry = { name: domainName, code: domainName, modules: [] }
          filteredDomainProducts.push(domainEntry)
          domainByName.set(domainName, domainEntry)
        }
        for (const [subDomainName, smMap] of sdMap) {
          let sdEntry = sdByKey.get(`${domainName}::${subDomainName}`)
          if (!sdEntry) {
            sdEntry = { name: subDomainName, code: subDomainName, submodules: [] }
            domainEntry.modules.push(sdEntry)
            sdByKey.set(`${domainName}::${subDomainName}`, sdEntry)
          }
          for (const [smCode, smInfo] of smMap) {
            let smEntry = smByKey.get(`${subDomainName}::${smCode}`)
            if (!smEntry) {
              smEntry = { name: smInfo.name, code: smCode, isCenter: false, businessObjects: smInfo.codes }
              sdEntry.submodules.push(smEntry)
              smByKey.set(`${subDomainName}::${smCode}`, smEntry)
            }
          }
        }
      }
    }

    return filteredDomainProducts
  }

  it('50 domains x 100 sd x 5 sm x 10000 bo (大场景)', () => {
    const domainProducts = []
    for (let d = 0; d < 50; d++) {
      const modules = []
      for (let sd = 0; sd < 100; sd++) {
        const submodules = []
        for (let sm = 0; sm < 5; sm++) {
          submodules.push({ name: `sm-${d}-${sd}-${sm}`, code: `sm-${d}-${sd}-${sm}` })
        }
        modules.push({ name: `sd-${d}-${sd}`, code: `sd-${d}-${sd}`, submodules })
      }
      domainProducts.push({ name: `domain-${d}`, code: `domain-${d}`, modules })
    }
    const businessObjects = []
    for (let i = 0; i < 10000; i++) {
      const smIdx = i % 50
      const dIdx = Math.floor(smIdx / 5)
      const sdIdx = smIdx % 5
      businessObjects.push({
        code: `BO${i}`, serviceModule: `sm-${dIdx}-${sdIdx}-${smIdx % 5}`,
        domain: `domain-${dIdx}`, subDomain: `sd-${dIdx}-${sdIdx}`
      })
    }
    const previewData = { domainProducts, businessObjects }
    const centerScope = Array.from({ length: 100 }, (_, i) => `BO${i}`)
    const relationFilteredBoCodes = []

    const t1 = performance.now()
    const r1 = filteredDomainProductsCurrent(previewData, centerScope, relationFilteredBoCodes)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = filteredDomainProductsOpt(previewData, centerScope, relationFilteredBoCodes)
    const tOpt = performance.now() - t2

    expect(r1.length).toBe(r2.length)
    console.log(`[filteredDomainProducts-50x100x5x10000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })

  it('小场景 5x5x5x500: 验证 fix 仍然有效', () => {
    const domainProducts = []
    for (let d = 0; d < 5; d++) {
      const modules = []
      for (let sd = 0; sd < 5; sd++) {
        const submodules = []
        for (let sm = 0; sm < 5; sm++) {
          submodules.push({ name: `sm-${d}-${sd}-${sm}`, code: `sm-${d}-${sd}-${sm}` })
        }
        modules.push({ name: `sd-${d}-${sd}`, code: `sd-${d}-${sd}`, submodules })
      }
      domainProducts.push({ name: `domain-${d}`, code: `domain-${d}`, modules })
    }
    const businessObjects = []
    for (let i = 0; i < 500; i++) {
      businessObjects.push({
        code: `BO${i}`, serviceModule: `sm-${i % 5}-${i % 5}-${i % 5}`,
        domain: `domain-${i % 5}`, subDomain: `sd-${i % 5}-${i % 5}`
      })
    }
    const previewData = { domainProducts, businessObjects }
    const centerScope = Array.from({ length: 50 }, (_, i) => `BO${i}`)

    const t1 = performance.now()
    const r1 = filteredDomainProductsCurrent(previewData, centerScope, null)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = filteredDomainProductsOpt(previewData, centerScope, null)
    const tOpt = performance.now() - t2

    expect(r1.length).toBe(r2.length)
    console.log(`[filteredDomainProducts-5x5x5x500] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})
