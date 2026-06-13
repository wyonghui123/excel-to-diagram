/**
 * 深入优化 benchmark - #6+ MermaidComponent + useDiagramData 热点
 */
import { describe, it, expect } from 'vitest'

// 1. MermaidComponent hideLinkLabelTails: 6 次 querySelectorAll + forEach
describe('MermaidComponent.hideLinkLabelTails (6 次 querySelectorAll)', () => {
  function hideLinkLabelTailsCurrent(svg) {
    // [模拟 MermaidComponent.vue:607-668]
    const bgRects = svg.querySelectorAll('[data-bg-rect="true"]')
    bgRects.forEach(rect => rect.setAttribute('style', 'display: none !important; visibility: hidden !important;'))
    const edgeLabelRects = svg.querySelectorAll('.edgeLabel rect, g.edgeLabel rect')
    edgeLabelRects.forEach(rect => rect.setAttribute('style', 'display: none !important; visibility: hidden !important;'))
    const edgeLabelPolygons = svg.querySelectorAll('.edgeLabel polygon, g.edgeLabel polygon')
    edgeLabelPolygons.forEach(poly => poly.setAttribute('style', 'display: none !important; visibility: hidden !important;'))
    const edgeLabelPaths = svg.querySelectorAll('.edgeLabel path, g.edgeLabel path')
    edgeLabelPaths.forEach(path => path.setAttribute('style', 'display: none !important; visibility: hidden !important;'))
    const lines = svg.querySelectorAll('line')
    lines.forEach(line => {
      const strokeDasharray = line.getAttribute('stroke-dasharray')
      if (strokeDasharray) line.setAttribute('style', 'display: none !important; visibility: hidden !important;')
    })
    const circles = svg.querySelectorAll('circle')
    circles.forEach(circle => {
      const r = circle.getAttribute('r')
      const fill = circle.getAttribute('fill')
      if (r && parseFloat(r) <= 5) circle.setAttribute('style', 'display: none !important; visibility: hidden !important;')
    })
  }

  // 优化: 用 CSS 一次性隐藏
  function hideLinkLabelTailsOpt(svg) {
    // [FIX-PERF] 注入 style 一次性隐藏, 避免 6 次 querySelectorAll
    const styleId = 'mermaid-hide-tails-style'
    if (!svg.querySelector(`#${styleId}`)) {
      const style = svg.ownerDocument.createElementNS('http://www.w3.org/2000/svg', 'style')
      style.id = styleId
      style.textContent = `
        [data-bg-rect="true"] { display: none !important; visibility: hidden !important; }
        .edgeLabel rect, .edgeLabel polygon, .edgeLabel path,
        g.edgeLabel rect, g.edgeLabel polygon, g.edgeLabel path { display: none !important; visibility: hidden !important; }
        line[stroke-dasharray] { display: none !important; visibility: hidden !important; }
        circle[r$="0"], circle[r$="1"], circle[r$="2"], circle[r$="3"], circle[r$="4"], circle[r$="5"] { display: none !important; visibility: hidden !important; }
      `
      svg.insertBefore(style, svg.firstChild)
    }
  }

  // 模拟大场景 SVG (5000 元素)
  function makeMockSvg(totalElements = 5000) {
    const elements = []
    // 5% bg-rects (250)
    for (let i = 0; i < totalElements * 0.05; i++) {
      elements.push({ tag: 'rect', attrs: { 'data-bg-rect': 'true' } })
    }
    // 20% edgeLabel rects/polygons/paths (1000)
    for (let i = 0; i < totalElements * 0.20; i++) {
      const types = ['rect', 'polygon', 'path']
      elements.push({ tag: types[i % 3], attrs: { class: 'edgeLabel' } })
    }
    // 30% lines with stroke-dasharray (1500)
    for (let i = 0; i < totalElements * 0.30; i++) {
      elements.push({ tag: 'line', attrs: { 'stroke-dasharray': '5,5' } })
    }
    // 10% circles with r<5 (500)
    for (let i = 0; i < totalElements * 0.10; i++) {
      elements.push({ tag: 'circle', attrs: { r: String(i % 5) } })
    }
    // 35% other (1750)
    for (let i = 0; i < totalElements * 0.35; i++) {
      elements.push({ tag: 'rect', attrs: { width: '100' } })
    }

    // 创建 SVG 模拟对象
    const mockSvg = {
      querySelectorAll: (selector) => {
        // 简化: 根据 selector 模拟
        if (selector.includes('data-bg-rect')) {
          return elements.filter(e => e.attrs['data-bg-rect'] === 'true')
        } else if (selector.includes('edgeLabel')) {
          return elements.filter(e => e.attrs.class === 'edgeLabel')
        } else if (selector === 'line') {
          return elements.filter(e => e.tag === 'line')
        } else if (selector === 'circle') {
          return elements.filter(e => e.tag === 'circle')
        }
        return []
      },
      ownerDocument: {
        createElementNS: (ns, tag) => {
          const el = {
            tagName: tag, textContent: '', id: '', firstChild: null,
            setAttribute: function(k, v) { this[k] = v },
            getAttribute: function(k) { return this[k] }
          }
          return el
        }
      },
      insertBefore: (node) => { /* mock */ },
      querySelector: (selector) => null,
      firstChild: null
    }

    // 给所有 elements 添加 setAttribute/getAttribute (因为 querySelectorAll 返回 elements)
    for (const e of elements) {
      e.setAttribute = function(k, v) { this.attrs[k] = v }
      e.getAttribute = function(k) { return this.attrs[k] }
    }
    return { svg: mockSvg, totalElements }
  }

  it('5000 元素 SVG: 当前 6 次 querySelectorAll vs 优化 CSS 注入', () => {
    const { svg } = makeMockSvg(5000)

    const t1 = performance.now()
    hideLinkLabelTailsCurrent(svg)
    const tCurrent = performance.now() - t1

    const { svg: svg2 } = makeMockSvg(5000)
    const t2 = performance.now()
    hideLinkLabelTailsOpt(svg2)
    const tOpt = performance.now() - t2

    console.log(`[hideLinkLabelTails-5000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })

  it('20000 元素 SVG: 大场景', () => {
    const { svg } = makeMockSvg(20000)

    const t1 = performance.now()
    hideLinkLabelTailsCurrent(svg)
    const tCurrent = performance.now() - t1

    const { svg: svg2 } = makeMockSvg(20000)
    const t2 = performance.now()
    hideLinkLabelTailsOpt(svg2)
    const tOpt = performance.now() - t2

    console.log(`[hideLinkLabelTails-20000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})

// 2. useDiagramData.updateCenterScopeMarkers: SM × BO O(n²)
describe('useDiagramData.updateCenterScopeMarkers (SM x BO O(n^2))', () => {
  function updateCenterScopeMarkersCurrent(smList, boList, centerScope, domainProducts) {
    const centerScopeSet = new Set(centerScope || [])
    const markers = { serviceModules: new Map(), subDomains: new Map(), domains: new Map() }
    if (centerScopeSet.size === 0) return markers

    // [BOTTLENECK] smList.forEach 内 .filter 10000 BO
    smList.forEach(sm => {
      const matchingBos = boList.filter(bo => bo.serviceModule === sm.code && centerScopeSet.has(bo.code))
      if (matchingBos && matchingBos.length > 0) {
        if (sm.name) markers.serviceModules.set(sm.name, true)
        if (sm.code) markers.serviceModules.set(sm.code, true)
      }
    })

    // 第二层: domainProducts 嵌套遍历
    domainProducts?.forEach(domain => {
      let domainHasCenter = false
      domain.modules?.forEach(subDomain => {
        let subDomainHasCenter = false
        subDomain.submodules?.forEach(module => {
          module.businessObjects?.forEach(bo => {
            const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
            if (centerScopeSet.has(boCode)) {
              subDomainHasCenter = true
              domainHasCenter = true
            }
          })
        })
        markers.subDomains.set(subDomain.name, subDomainHasCenter)
      })
      markers.domains.set(domain.name, domainHasCenter)
    })

    return markers
  }

  function updateCenterScopeMarkersOpt(smList, boList, centerScope, domainProducts) {
    const centerScopeSet = new Set(centerScope || [])
    const markers = { serviceModules: new Map(), subDomains: new Map(), domains: new Map() }
    if (centerScopeSet.size === 0) return markers

    // [FIX-PERF] 预建 boBySm Map O(n)
    const boBySm = new Map()
    for (const bo of boList) {
      if (!boBySm.has(bo.serviceModule)) boBySm.set(bo.serviceModule, [])
      boBySm.get(bo.serviceModule).push(bo)
    }

    smList.forEach(sm => {
      const smBos = boBySm.get(sm.code) || []
      let hasCenter = false
      for (const bo of smBos) if (centerScopeSet.has(bo.code)) { hasCenter = true; break }
      if (hasCenter) {
        if (sm.name) markers.serviceModules.set(sm.name, true)
        if (sm.code) markers.serviceModules.set(sm.code, true)
      }
    })

    domainProducts?.forEach(domain => {
      let domainHasCenter = false
      domain.modules?.forEach(subDomain => {
        let subDomainHasCenter = false
        subDomain.submodules?.forEach(module => {
          module.businessObjects?.forEach(bo => {
            const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
            if (centerScopeSet.has(boCode)) {
              subDomainHasCenter = true
              domainHasCenter = true
            }
          })
        })
        markers.subDomains.set(subDomain.name, subDomainHasCenter)
      })
      markers.domains.set(domain.name, domainHasCenter)
    })

    return markers
  }

  it('1000 SM x 10000 BO: 当前 vs 优化', () => {
    const smList = Array.from({ length: 1000 }, (_, i) => ({ code: `SM${i}`, name: `SM Name ${i}` }))
    const boList = []
    for (let i = 0; i < 10000; i++) {
      boList.push({ code: `BO${i}`, serviceModule: `SM${i % 1000}` })
    }
    const centerScope = Array.from({ length: 100 }, (_, i) => `BO${i}`)
    const domainProducts = []

    const t1 = performance.now()
    const r1 = updateCenterScopeMarkersCurrent(smList, boList, centerScope, domainProducts)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = updateCenterScopeMarkersOpt(smList, boList, centerScope, domainProducts)
    const tOpt = performance.now() - t2

    expect(r1.serviceModules.size).toBe(r2.serviceModules.size)
    console.log(`[updateCenterScopeMarkers-1000x10000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})

// 3. useDiagramData.filteredContainers.hasAnyBo: SM × BO O(n²)
describe('useDiagramData.filteredContainers.hasAnyBo (SM x BO O(n^2))', () => {
  function filteredHasAnyBoCurrent(smList, boList, finalBoCodes) {
    const result = []
    // [BOTTLENECK] smList.forEach 内 .some 10000 BO
    smList.forEach(sm => {
      const hasAnyBo = boList.some(bo => bo.serviceModule === sm.code && finalBoCodes.has(bo.code))
      if (hasAnyBo) result.push(sm)
    })
    return result
  }

  function filteredHasAnyBoOpt(smList, boList, finalBoCodes) {
    const result = []
    const boBySm = new Map()
    for (const bo of boList) {
      if (!boBySm.has(bo.serviceModule)) boBySm.set(bo.serviceModule, [])
      boBySm.get(bo.serviceModule).push(bo)
    }
    for (const sm of smList) {
      const smBos = boBySm.get(sm.code) || []
      for (const bo of smBos) {
        if (finalBoCodes.has(bo.code)) { result.push(sm); break }
      }
    }
    return result
  }

  it('1000 SM x 10000 BO', () => {
    const smList = Array.from({ length: 1000 }, (_, i) => ({ code: `SM${i}`, name: `SM Name ${i}` }))
    const boList = []
    for (let i = 0; i < 10000; i++) {
      boList.push({ code: `BO${i}`, serviceModule: `SM${i % 1000}` })
    }
    const finalBoCodes = new Set(Array.from({ length: 100 }, (_, i) => `BO${i}`))

    const t1 = performance.now()
    const r1 = filteredHasAnyBoCurrent(smList, boList, finalBoCodes)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = filteredHasAnyBoOpt(smList, boList, finalBoCodes)
    const tOpt = performance.now() - t2

    expect(r1.length).toBe(r2.length)
    console.log(`[filteredHasAnyBo-1000x10000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})

// 4. MermaidComponent.getNestingLevel: O(nesting x subgraphs.length)
describe('MermaidComponent.getNestingLevel (O(nesting x subgraphs.length))', () => {
  function getNestingLevelCurrent(subgraph, subgraphs) {
    let level = 0
    let parent = subgraph.parentElement
    while (parent) {
      // [BOTTLENECK] subgraphs.includes(parent) O(n)
      if (parent.tagName === 'g' && subgraphs.includes(parent)) {
        level++
      }
      parent = parent.parentElement
    }
    return level
  }

  function getNestingLevelOpt(subgraph, subgraphs) {
    // [FIX-PERF] 预建 Set O(1)
    const subgraphSet = subgraphs  // 假设传入 Set
    let level = 0
    let parent = subgraph.parentElement
    while (parent) {
      if (parent.tagName === 'g' && subgraphSet.has(parent)) {
        level++
      }
      parent = parent.parentElement
    }
    return level
  }

  it('100 subgraphs + nesting 4: 当前 vs 优化', () => {
    // 模拟: 100 g elements with parent chain
    const subgraphs = []
    let root = { tagName: 'svg', parentElement: null }
    for (let i = 0; i < 100; i++) {
      const g = { tagName: 'g', parentElement: root }
      subgraphs.push(g)
      root = g
    }

    const t1 = performance.now()
    for (const s of subgraphs) {
      getNestingLevelCurrent(s, subgraphs)
    }
    const tCurrent = performance.now() - t1

    const subgraphSet = new Set(subgraphs)
    const t2 = performance.now()
    for (const s of subgraphs) {
      getNestingLevelOpt(s, subgraphSet)
    }
    const tOpt = performance.now() - t2

    console.log(`[getNestingLevel-100] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})

// 5. MermaidComponent watcher: JSON.stringify in watch diff
describe('MermaidComponent watcher (JSON.stringify diff)', () => {
  it('1000 nodes: JSON.stringify 成本', () => {
    const nodes = Array.from({ length: 1000 }, (_, i) => ({
      id: `n-${i}`, name: `Node ${i}`, code: `N${i}`,
      domain: `D${i % 20}`, subDomain: `SD${i % 100}`, serviceModule: `SM${i % 500}`,
      isCenter: i % 3 === 0
    }))
    const links = Array.from({ length: 2000 }, (_, i) => ({
      source: `n-${i % 1000}`, target: `n-${(i * 7) % 1000}`,
      sourceCode: `N${i % 1000}`, targetCode: `N${(i * 7) % 1000}`
    }))
    const customColors = {}
    for (let i = 0; i < 20; i++) customColors[`D${i}`] = `#${i}${i}${i}`

    const t1 = performance.now()
    const nodesStr = JSON.stringify(nodes)
    const linksStr = JSON.stringify(links)
    const customStr = JSON.stringify(customColors)
    const tCurrent = performance.now() - t1

    console.log(`[watcher-JSON.stringify] ${tCurrent.toFixed(2)}ms (3 次 JSON.stringify)`)
    console.log(`  nodes: ${nodesStr.length} chars, links: ${linksStr.length} chars, custom: ${customStr.length} chars`)
  })
})
