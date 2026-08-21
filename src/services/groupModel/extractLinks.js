/**
 * extractLinks - 从扁平 relationships 提取 Link 数组
 *
 * [来源] 7/31 13:04 Trae History: -35658d4d/ZQZJ.js (Phase 5/6)
 * [契约] 见 chart-data-flow-and-interaction-upgrade.md §5.10.2 ②
 */
export function extractLinks(relationships) {
  if (!Array.isArray(relationships)) return []

  const seen = new Set()
  const links = []

  for (const rel of relationships) {
    if (!rel || typeof rel !== 'object') continue

    // 兼容 snake_case 和 camelCase
    const source = rel.sourceCode ?? rel.source_code ?? rel.source_bo_id ?? rel.source ?? null
    const target = rel.targetCode ?? rel.target_code ?? rel.target_bo_id ?? rel.target ?? null
    const relationCode = rel.relationCode ?? rel.relation_code ?? null

    // 边界 1: sourceCode/targetCode 为空跳过
    if (!source || !target) continue

    // 边界 2: 自环跳过
    if (source === target) continue

    // 边界 3: 同 source/target/relationCode 去重
    const dedupeKey = `${source}|${target}|${relationCode || ''}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)

    // 反向关系不视为重复（key 不同）

    const label = rel.label ?? rel.relationDesc ?? rel.relation_desc ?? relationCode ?? ''
    const categoryTypes = rel.categoryTypes ?? rel.category_types ?? rel.annotationCategories ?? rel.annotation_categories ?? []
    const annotationContents = rel.annotationContents ?? rel.annotation_contents ?? []

    links.push({
      source,
      target,
      relationCode,
      label,
      categoryTypes,
      annotationContents,
      relationDesc: rel.relationDesc ?? rel.relation_desc ?? ''
    })
  }

  return links
}
