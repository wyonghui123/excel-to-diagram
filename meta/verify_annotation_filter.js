/**
 * 验证 annotation 过滤修复 (2026-06-30)
 *
 * Issue 1: 配置阶段不选备注类型时, 图表中不展示任何备注
 * Issue 2: 连线标签 tooltip 只展示过滤后的备注内容
 *
 * 运行: node meta/verify_annotation_filter.js
 */

// 模拟 useAnnotation.parseAnnotationsFromData 的过滤逻辑
function simulateParseFilter(data, filter = []) {
  const result = []
  let number = 1

  function pushAnnotation(targetType, targetId, contents, categories) {
    if (!Array.isArray(contents) || contents.length === 0) return
    contents.forEach((content, idx) => {
      if (!content) return
      const category = (Array.isArray(categories) && categories[idx]) || 'info'
      result.push({
        id: `ANN${String(number).padStart(3, '0')}`,
        number: number++,
        targetType,
        targetId,
        category,
        content
      })
    })
  }

  if (data.nodes) {
    data.nodes.forEach(node => {
      pushAnnotation('node', node.code, node.annotationContents, node.annotationCategories)
    })
  }
  if (data.links) {
    data.links.forEach(link => {
      pushAnnotation('relation', link.code, link.annotationContents, link.annotationCategories)
    })
  }

  // [新逻辑] filter=[] => 空, filter 非空 => 按 category 过滤
  const filteredResult = (Array.isArray(filter) && filter.length > 0)
    ? result.filter(ann => ann.category && filter.includes(ann.category))
    : []

  return { total: result.length, filtered: filteredResult.length, items: filteredResult }
}

// 模拟 useTooltip.formatTooltipText 的过滤逻辑
function simulateTooltipFilter(relation, annotationFilter) {
  let annotationLine = ''
  if (annotationFilter === undefined) {
    annotationLine = relation.annotationContent || ''
  } else if (Array.isArray(annotationFilter) && annotationFilter.length > 0) {
    const contents = relation.annotationContents
    const categories = relation.annotationCategories
    if (Array.isArray(contents) && contents.length > 0 && Array.isArray(categories)) {
      const matched = contents
        .map((c, idx) => ({ content: c, category: categories[idx] || 'info' }))
        .filter(item => item.content && item.category && annotationFilter.includes(item.category))
        .map(item => item.content)
      annotationLine = matched.join('; ')
    } else if (relation.annotationContent && relation.annotationCategory && annotationFilter.includes(relation.annotationCategory)) {
      annotationLine = relation.annotationContent
    }
  }

  return annotationLine ? `备注: ${annotationLine}` : '(无备注行)'
}

// ========== 测试数据 ==========
const testData = {
  nodes: [
    {
      code: 'BO_A',
      annotationContents: ['节点A的审计备注', '节点A的信息备注'],
      annotationCategories: ['AUDIT', 'INFO']
    }
  ],
  links: [
    {
      code: 'REL_A_B',
      annotationContents: ['关系A→B的审计备注', '关系A→B的信息备注', '关系A→B的测试备注'],
      annotationCategories: ['AUDIT', 'INFO', 'TEST']
    }
  ]
}

// ========== Issue 1 验证 ==========
console.log('=== Issue 1: 配置阶段不选备注类型时不展示任何备注 ===\n')

const issue1Case1 = simulateParseFilter(testData, [])
console.log(`[Case 1] filter=[] (用户未选)`)
console.log(`  total=${issue1Case1.total}, filtered=${issue1Case1.filtered}`)
console.log(`  ${issue1Case1.filtered === 0 ? '✓ PASS' : '✗ FAIL'}: 期望 filtered=0, 实际 filtered=${issue1Case1.filtered}\n`)

const issue1Case2 = simulateParseFilter(testData, ['AUDIT'])
console.log(`[Case 2] filter=['AUDIT']`)
console.log(`  total=${issue1Case2.total}, filtered=${issue1Case2.filtered}`)
console.log(`  items: ${issue1Case2.items.map(i => `${i.targetType}:${i.category}:${i.content}`).join(' | ')}`)
const case2Pass = issue1Case2.filtered === 2 && issue1Case2.items.every(i => i.category === 'AUDIT')
console.log(`  ${case2Pass ? '✓ PASS' : '✗ FAIL'}: 期望 filtered=2 且全部 AUDIT\n`)

const issue1Case3 = simulateParseFilter(testData, ['AUDIT', 'TEST'])
console.log(`[Case 3] filter=['AUDIT', 'TEST']`)
console.log(`  total=${issue1Case3.total}, filtered=${issue1Case3.filtered}`)
console.log(`  items: ${issue1Case3.items.map(i => `${i.targetType}:${i.category}:${i.content}`).join(' | ')}`)
// 期望: 1 node AUDIT + 1 relation AUDIT + 1 relation TEST = 3, 不含 INFO
const case3Pass = issue1Case3.filtered === 3
  && issue1Case3.items.some(i => i.category === 'TEST')
  && issue1Case3.items.every(i => i.category !== 'INFO')
console.log(`  ${case3Pass ? '✓ PASS' : '✗ FAIL'}: 期望 filtered=3, 含 TEST 类, 不含 INFO\n`)

// ========== Issue 2 验证 ==========
console.log('=== Issue 2: 连线标签 tooltip 只展示过滤后的备注 ===\n')

const rel = testData.links[0]
console.log(`[关系数据] relationCode=${rel.code}`)
console.log(`  annotationContents: ${JSON.stringify(rel.annotationContents)}`)
console.log(`  annotationCategories: ${JSON.stringify(rel.annotationCategories)}\n`)

const issue2Case1 = simulateTooltipFilter(rel, [])
console.log(`[Case 1] annotationFilter=[] (用户未选)`)
console.log(`  tooltip 备注: ${issue2Case1}`)
const case1Pass2 = issue2Case1 === '(无备注行)'
console.log(`  ${case1Pass2 ? '✓ PASS' : '✗ FAIL'}: 期望无备注行\n`)

const issue2Case2 = simulateTooltipFilter(rel, ['AUDIT'])
console.log(`[Case 2] annotationFilter=['AUDIT']`)
console.log(`  tooltip 备注: ${issue2Case2}`)
const case2Pass2 = issue2Case2 === '备注: 关系A→B的审计备注'
console.log(`  ${case2Pass2 ? '✓ PASS' : '✗ FAIL'}: 期望仅显示 AUDIT 备注\n`)

const issue2Case3 = simulateTooltipFilter(rel, ['AUDIT', 'TEST'])
console.log(`[Case 3] annotationFilter=['AUDIT', 'TEST']`)
console.log(`  tooltip 备注: ${issue2Case3}`)
const case3Pass2 = issue2Case2 === '备注: 关系A→B的审计备注; 关系A→B的测试备注' || issue2Case3.includes('审计备注') && issue2Case3.includes('测试备注') && !issue2Case3.includes('信息备注')
console.log(`  ${case3Pass2 ? '✓ PASS' : '✗ FAIL'}: 期望显示 AUDIT+TEST, 不显示 INFO\n`)

const issue2Case4 = simulateTooltipFilter(rel, ['INFO'])
console.log(`[Case 4] annotationFilter=['INFO'] (只选 INFO)`)
console.log(`  tooltip 备注: ${issue2Case4}`)
const case4Pass = issue2Case4 === '备注: 关系A→B的信息备注'
console.log(`  ${case4Pass ? '✓ PASS' : '✗ FAIL'}: 期望仅显示 INFO 备注\n`)

// ========== 向后兼容验证 ==========
console.log('=== 向后兼容: formatTooltipText(relation) 未传 filter ===\n')

const compatCase = simulateTooltipFilter({ annotationContent: '旧字段备注' }, undefined)
console.log(`[兼容] annotationFilter=undefined, relation.annotationContent='旧字段备注'`)
console.log(`  tooltip 备注: ${compatCase}`)
const compatPass = compatCase === '备注: 旧字段备注'
console.log(`  ${compatPass ? '✓ PASS' : '✗ FAIL'}: 期望显示旧字段备注 (单测兼容)\n`)

// ========== 总结 ==========
const allPass = [
  issue1Case1.filtered === 0,
  case2Pass,
  case3Pass,
  case1Pass2,
  case2Pass2,
  case3Pass2,
  case4Pass,
  compatPass
].every(Boolean)

console.log('=== 总结 ===')
console.log(allPass ? '✓ 所有测试通过' : '✗ 存在失败用例')
process.exit(allPass ? 0 : 1)
