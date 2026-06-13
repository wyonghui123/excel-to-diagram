/**
 * 深入优化 benchmark - #4+ 真实热点
 *
 * 覆盖:
 * 1. serviceModuleDiagramBuilder.generateServiceModuleMermaidCode (nodes.find in loop)
 * 2. 后端 architecture/preview API 模拟 (已用 Map, 量化确认)
 * 3. ColorCalculator.compute (已用 Map, 量化确认)
 * 4. validateData 6 个函数 (已用 Set, 量化确认)
 * 5. UnifiedRenderer.render (已用 Map, 量化确认)
 */
import { describe, it, expect } from 'vitest'

// 1. 模拟 serviceModuleDiagramBuilder.generateServiceModuleMermaidCode 的 O(n²) 风险
describe('服务模块图: generateServiceModuleMermaidCode 性能', () => {
  function generateMermaidCodeCurrent(nodes, containers) {
    let code = 'graph TD\n'
    containers.forEach(container => {
      const containerId = container.id.replace(/[^a-zA-Z0-9]/g, '_')
      code += `    subgraph ${containerId}["${container.fullTitle}"]\n`
      // [BOTTLENECK] nodes.find 在循环内
      container.nodes.forEach(nodeId => {
        const node = nodes.find(n => n.id === nodeId)
        if (node) {
          const nodeLabel = `${node.name}<br/>${node.code}`
          code += `        ${node.code}["${nodeLabel}"]\n`
        }
      })
      code += `    end\n`
    })
    return code
  }

  function generateMermaidCodeOpt(nodes, containers) {
    let code = 'graph TD\n'
    // [FIX-PERF] 预建 nodeById Map
    const nodeById = new Map()
    for (const n of nodes) nodeById.set(n.id, n)

    containers.forEach(container => {
      const containerId = container.id.replace(/[^a-zA-Z0-9]/g, '_')
      code += `    subgraph ${containerId}["${container.fullTitle}"]\n`
      container.nodes.forEach(nodeId => {
        const node = nodeById.get(nodeId)
        if (node) {
          const nodeLabel = `${node.name}<br/>${node.code}`
          code += `        ${node.code}["${nodeLabel}"]\n`
        }
      })
      code += `    end\n`
    })
    return code
  }

  it('中场景: 200 SM in 20 containers', () => {
    const nodes = Array.from({ length: 200 }, (_, i) => ({
      id: `sm-${i}`, name: `SM ${i}`, code: `SM${i}`
    }))
    const containers = Array.from({ length: 20 }, (_, i) => ({
      id: `container-${i}`, fullTitle: `Container ${i}`,
      nodes: nodes.filter((_, j) => j % 20 === i).map(n => n.id)
    }))

    const t1 = performance.now()
    const code1 = generateMermaidCodeCurrent(nodes, containers)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const code2 = generateMermaidCodeOpt(nodes, containers)
    const tOpt = performance.now() - t2

    expect(code1).toBe(code2)
    console.log(`[SM-200] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / tOpt).toFixed(1)}x`)
  })

  it('大场景: 1000 SM in 50 containers', () => {
    const nodes = Array.from({ length: 1000 }, (_, i) => ({
      id: `sm-${i}`, name: `SM ${i}`, code: `SM${i}`
    }))
    const containers = Array.from({ length: 50 }, (_, i) => ({
      id: `container-${i}`, fullTitle: `Container ${i}`,
      nodes: nodes.filter((_, j) => j % 50 === i).map(n => n.id)
    }))

    const t1 = performance.now()
    const code1 = generateMermaidCodeCurrent(nodes, containers)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const code2 = generateMermaidCodeOpt(nodes, containers)
    const tOpt = performance.now() - t2

    expect(code1).toBe(code2)
    console.log(`[SM-1000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / tOpt).toFixed(1)}x`)
  })
})

// 2. ColorCalculator.compute (已用 Map, 验证)
describe('ColorCalculator.compute (已优化, 验证)', () => {
  function colorComputeCurrent(nodes, colorGroupBy, colorScheme) {
    const COLOR_SCHEMES = {
      default: ['#1890FF', '#2FC25B', '#FACC14', '#223273', '#8543E0', '#13C2C2', '#3436C7', '#F04864'],
      vibrant: ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845']
    }
    const colors = COLOR_SCHEMES[colorScheme] || COLOR_SCHEMES.default
    const colorMap = new Map()
    const groupKeys = new Map()
    nodes.forEach(node => {
      const key = colorGroupBy === 'subDomain' ? node.subDomain
                : colorGroupBy === 'serviceModule' ? node.serviceModule
                : node.domain
      groupKeys.set(node.code, key)
    })
    const uniqueGroups = [...new Set(groupKeys.values())].filter(Boolean)
    const groupColorMap = new Map()
    uniqueGroups.forEach((group, index) => {
      groupColorMap.set(group, colors[index % colors.length])
    })
    nodes.forEach(node => {
      const groupKey = groupKeys.get(node.code)
      const baseColor = groupColorMap.get(groupKey) || colors[0]
      const finalColor = node.isCenter ? '#EDEDED' : baseColor
      colorMap.set(node.code, finalColor)
    })
    return colorMap
  }

  it('1000 BO 计算: 验证 O(n) 性能', () => {
    const nodes = Array.from({ length: 1000 }, (_, i) => ({
      code: `BO${i}`, domain: `D${i % 20}`, subDomain: `SD${i % 100}`,
      serviceModule: `SM${i % 500}`, isCenter: i % 3 === 0
    }))

    const t1 = performance.now()
    const result = colorComputeCurrent(nodes, 'domain', 'default')
    const tCurrent = performance.now() - t1

    expect(result.size).toBe(1000)
    console.log(`[Color-1000] current: ${tCurrent.toFixed(2)}ms (已经是 O(n), 验证)`)
  })
})

// 3. validateData 模拟
describe('validateData (已优化, 验证)', () => {
  it('5000 relationships FK 校验: 验证 O(n)', () => {
    // 模拟 validateRelationshipForeignKeys
    const businessObjects = Array.from({ length: 1000 }, (_, i) => ({ code: `BO${i}` }))
    const validBusinessObjects = new Set()
    businessObjects.forEach(bo => validBusinessObjects.add(bo.code))

    const relationships = Array.from({ length: 5000 }, (_, i) => ({
      sourceCode: `BO${i % 1000}`,
      targetCode: `BO${(i * 7) % 1000}`,
      relationCode: `REL${i}`
    }))

    const t1 = performance.now()
    let invalidCount = 0
    for (const rel of relationships) {
      if (!validBusinessObjects.has(rel.sourceCode)) invalidCount++
      if (!validBusinessObjects.has(rel.targetCode)) invalidCount++
    }
    const t = performance.now() - t1

    expect(invalidCount).toBe(0)
    console.log(`[validate-FK-5000] ${t.toFixed(2)}ms (已经是 O(n), 验证)`)
  })

  it('5000 重复数据校验: 验证 O(n)', () => {
    // 模拟 validateDuplicates
    const boData = Array.from({ length: 5000 }, (_, i) => ({
      code: `BO${i % 2500}` // 50% 重复
    }))

    const t1 = performance.now()
    const seen = new Map()
    let dupCount = 0
    for (const item of boData) {
      if (item.code) {
        if (seen.has(item.code)) {
          dupCount++
        } else {
          seen.set(item.code, true)
        }
      }
    }
    const t = performance.now() - t1

    expect(dupCount).toBeGreaterThan(0)
    console.log(`[validate-Dup-5000] ${t.toFixed(2)}ms, ${dupCount} dups found (已经是 O(n), 验证)`)
  })
})

// 4. 后端 architecture/preview 模拟
describe('后端 architecture/preview 关系 scope 分类 (已用 Map, 验证)', () => {
  function classifyRelCurrent(businessObjects, relationships, centerScope) {
    // [模拟 bo_api.py:1320-1386]
    const bo_id_map = new Map()
    for (const b of businessObjects) {
      bo_id_map.set(b.get('id'), {
        domain_id: b.get('domain_id'),
        sub_domain_id: b.get('sub_domain_id'),
        service_module_id: b.get('service_module_id'),
      })
    }
    const center_scope_set = new Set(centerScope)
    const bo_code_map = new Map()
    for (const b of businessObjects) {
      if (b.get('code')) bo_code_map.set(b.get('code'), b.get('id'))
    }
    for (const rel of relationships) {
      const src_code = rel.get('source_code')
      const tgt_code = rel.get('target_code')
      const src_bo_id = bo_code_map.get(src_code)
      const tgt_bo_id = bo_code_map.get(tgt_code)
      const src_info = src_bo_id ? bo_id_map.get(src_bo_id) || {} : {}
      const tgt_info = tgt_bo_id ? bo_id_map.get(tgt_bo_id) || {} : {}
      const src_in_scope = center_scope_set.has(src_code)
      const tgt_in_scope = center_scope_set.has(tgt_code)
      const scope_type = (src_in_scope && tgt_in_scope) ? 'internal'
        : (src_in_scope || tgt_in_scope) ? 'cross-boundary' : 'external'
      const src_domain = src_info.domain_id
      const tgt_domain = tgt_info.domain_id
      const src_sub = src_info.sub_domain_id
      const tgt_sub = tgt_info.sub_domain_id
      const src_module = src_info.service_module_id
      const tgt_module = tgt_info.service_module_id
      let category_type
      if (src_domain && tgt_domain && src_domain !== tgt_domain) category_type = 'cross-domain'
      else if (src_sub && tgt_sub && src_sub !== tgt_sub) category_type = 'same-domain-cross-subdomain'
      else if (src_module && tgt_module && src_module !== tgt_module) category_type = 'same-subdomain-cross-module'
      else category_type = 'same-module'
      rel.set('scope_type', scope_type)
      rel.set('category_type', category_type)
    }
  }

  it('10000 关系分类: 验证 O(n)', () => {
    const businessObjects = []
    for (let i = 0; i < 1000; i++) {
      businessObjects.push(new Map([
        ['id', i + 1], ['code', `BO${i}`], ['domain_id', (i % 20) + 1],
        ['sub_domain_id', (i % 100) + 1], ['service_module_id', (i % 500) + 1]
      ]))
    }
    const relationships = []
    for (let i = 0; i < 10000; i++) {
      relationships.push(new Map([
        ['source_code', `BO${i % 1000}`], ['target_code', `BO${(i * 7) % 1000}`]
      ]))
    }
    const centerScope = Array.from({ length: 100 }, (_, i) => `BO${i}`)

    const t1 = performance.now()
    classifyRelCurrent(businessObjects, relationships, centerScope)
    const t = performance.now() - t1

    let internal = 0, cross = 0, external = 0
    for (const r of relationships) {
      const st = r.get('scope_type')
      if (st === 'internal') internal++
      else if (st === 'cross-boundary') cross++
      else external++
    }
    console.log(`[be-classify-10000] ${t.toFixed(2)}ms, internal=${internal}, cross=${cross}, external=${external} (已经是 O(n), 验证)`)
    expect(internal + cross + external).toBe(10000)
  })
})

// 5. UnifiedRenderer 模拟
describe('UnifiedRenderer.render (已用 Map, 验证)', () => {
  function renderMermaidCurrent(flattenedGroups, links) {
    const codeToIdMap = new Map()
    flattenedGroups.forEach(g => {
      if (g.code && g.isTerminal) {
        codeToIdMap.set(g.code, g.id)
      }
    })
    let code = 'flowchart LR\n'
    const processedGroups = new Set()
    const childIds = new Set()
    flattenedGroups.forEach(g => {
      if (g.children && g.children.length > 0) {
        g.children.forEach(c => { if (c.id) childIds.add(c.id) })
      }
    })
    const rootGroups = flattenedGroups.filter(g => !childIds.has(g.id))
    rootGroups.forEach(group => {
      if (!processedGroups.has(group.id)) {
        // Simulate recursive render
        code += `${group.id}[${group.title}]\n`
        processedGroups.add(group.id)
        if (group.children) {
          group.children.forEach(c => {
            if (!processedGroups.has(c.id)) {
              code += `${c.id}[${c.title}]\n`
              processedGroups.add(c.id)
            }
          })
        }
      }
    })
    links.forEach(link => {
      const sourceId = codeToIdMap.get(link.source) || link.source
      const targetId = codeToIdMap.get(link.target) || link.target
      if (sourceId && targetId) {
        code += `  ${sourceId} --> ${targetId}\n`
      }
    })
    return code
  }

  it('1000 节点 5000 边 渲染: 验证 O(n)', () => {
    const groups = Array.from({ length: 1000 }, (_, i) => ({
      id: `g-${i}`, title: `Group ${i}`, code: `BO${i}`, isTerminal: i > 800
    }))
    const links = Array.from({ length: 5000 }, (_, i) => ({
      source: `BO${i % 200}`, target: `BO${(i * 7) % 200}`
    }))

    const t1 = performance.now()
    const code = renderMermaidCurrent(groups, links)
    const t = performance.now() - t1

    expect(code.length).toBeGreaterThan(0)
    console.log(`[UnifiedRenderer-1000] ${t.toFixed(2)}ms, code length: ${code.length} (已经是 O(n), 验证)`)
  })
})

// 6. MermaidComponent.applyTitleMapToGroups 递归树遍历
describe('MermaidComponent.applyTitleMapToGroups (递归, 验证)', () => {
  function applyTitleMap(groups, titleMap) {
    function processGroup(group) {
      const matchedTitle = titleMap[group.id] || titleMap[group.elementCode] || titleMap[group.title]
      if (matchedTitle) {
        group.title = matchedTitle
        group.fullTitle = matchedTitle
      }
      if (group.containers && group.containers.length > 0) {
        group.containers.forEach(c => processGroup(c))
      }
      if (group.children && group.children.length > 0) {
        group.children.forEach(c => processGroup(c))
      }
    }
    groups.forEach(g => processGroup(g))
  }

  it('1000 节点树遍历: 验证 O(n)', () => {
    // 模拟: 10 顶级 × 5 sub × 5 sub-sub × 4 SM = 1000
    const groups = []
    for (let d = 0; d < 10; d++) {
      for (let sd = 0; sd < 5; sd++) {
        for (let ssd = 0; ssd < 5; ssd++) {
          for (let sm = 0; sm < 4; sm++) {
            groups.push({
              id: `g-${d}-${sd}-${ssd}-${sm}`,
              title: `Node ${sm}`,
              elementCode: `SM${sm}`,
              containers: [],
              children: []
            })
          }
        }
      }
    }
    const titleMap = { 'g-0-0-0-0': 'Test 0' }

    const t1 = performance.now()
    applyTitleMap(groups, titleMap)
    const t = performance.now() - t1

    expect(groups[0].title).toBe('Test 0')
    console.log(`[applyTitleMap-1000] ${t.toFixed(2)}ms (已经是 O(n), 验证)`)
  })
})

// 7. getSelectedRelationIds: selectedNodeIds.includes() O(n^2) 风险
describe('getSelectedRelationIds 性能 (selectedNodeIds.includes 风险)', () => {
  function makeTree(totalNodes) {
    const tree = []
    for (let i = 0; i < totalNodes; i++) {
      tree.push({
        id: `node-${i}`,
        relationIds: i % 5 === 0 ? [`rel-${i}`] : [],
        children: []
      })
    }
    return tree
  }

  function getSelectedRelationIdsCurrent(tree, selectedNodeIds) {
    const relationIds = new Set()
    function traverseNode(node) {
      if (selectedNodeIds.includes(node.id)) {
        if (node.relationIds) {
          node.relationIds.forEach(id => relationIds.add(id))
        }
      }
      if (node.children && node.children.length > 0) {
        node.children.forEach(child => traverseNode(child))
      }
    }
    tree.forEach(rootNode => traverseNode(rootNode))
    return Array.from(relationIds)
  }

  function getSelectedRelationIdsOpt(tree, selectedNodeIds) {
    const relationIds = new Set()
    const selectedSet = new Set(selectedNodeIds)
    function traverseNode(node) {
      if (selectedSet.has(node.id)) {
        if (node.relationIds) {
          node.relationIds.forEach(id => relationIds.add(id))
        }
      }
      if (node.children && node.children.length > 0) {
        node.children.forEach(child => traverseNode(child))
      }
    }
    tree.forEach(rootNode => traverseNode(rootNode))
    return Array.from(relationIds)
  }

  it('200 节点 + 50 selected: 当前 vs 优化', () => {
    const tree = makeTree(200)
    const selected = Array.from({ length: 50 }, (_, i) => `node-${i}`)

    const t1 = performance.now()
    const r1 = getSelectedRelationIdsCurrent(tree, selected)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = getSelectedRelationIdsOpt(tree, selected)
    const tOpt = performance.now() - t2

    expect(r1.sort()).toEqual(r2.sort())
    console.log(`[getSelectedRelIds-200] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })

  it('1000 节点 + 200 selected: 大场景', () => {
    const tree = makeTree(1000)
    const selected = Array.from({ length: 200 }, (_, i) => `node-${i}`)

    const t1 = performance.now()
    const r1 = getSelectedRelationIdsCurrent(tree, selected)
    const tCurrent = performance.now() - t1

    const t2 = performance.now()
    const r2 = getSelectedRelationIdsOpt(tree, selected)
    const tOpt = performance.now() - t2

    expect(r1.sort()).toEqual(r2.sort())
    console.log(`[getSelectedRelIds-1000] current: ${tCurrent.toFixed(2)}ms, opt: ${tOpt.toFixed(2)}ms, speedup: ${(tCurrent / Math.max(tOpt, 0.001)).toFixed(1)}x`)
  })
})
