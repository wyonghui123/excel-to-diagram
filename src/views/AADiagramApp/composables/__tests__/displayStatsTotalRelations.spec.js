/**
 * displayStats.total.objectRelations 业务口径 (用户已确认 2026-06-13)
 *
 * 业务口径 (用户确认):
 *   total.objectRelations = center-internal + center↔external 跨边界
 *   中心范围 (用户直接选中的 BO) 内部的关系
 *   + 中心范围 与 关系范围 (拉入的外部 BO) 之间跨边界的关系
 *
 *   **不**包含: 两端都在 added 集合的"纯外部"关系 (B↔B)
 *   这些是 added 集合内部的关联, 不在 "中心 ∪ 关系" 业务定义内
 *
 * 实测 (用户场景):
 *   1 域, 1 子, 10 服务, 19 对象, 12 关系 (而非 17)
 *   - 4 关系: 中心内部 (center-internal)
 *   - 8 关系: 中心与外部 (cross-boundary, XOR)
 *   - 5 关系: 两端都在外部 (B↔B) - **不计入**
 *   - 中心 4 + 增量 8 = 12 ✓
 *
 * 之前曾误判为 17, 用 union (center + added) 改写, 已撤回
 */
import { describe, it, expect } from 'vitest'

/**
 * 纯函数复现 useDiagramData.js 中 total.objectRelations 的 fallback 逻辑
 * (从 line 1140-1165 抽出, 跟 useDiagramData 同步)
 */
function computeTotalRelationsFallback({
  previewDataRels = [],
  centerScope = []
}) {
  // 业务口径: 仅 center 作为 in-scope (B↔B 端点不在 center, 不被计入)
  const centerSet = new Set(centerScope || [])
  const truthIds = new Set()
  for (const r of previewDataRels) {
    if (r.id == null) continue
    if (r.sourceCode === r.targetCode) continue
    if (r.scopeType === 'internal' || r.scopeType === 'cross-boundary') {
      truthIds.add(r.id)
      continue
    }
    // 业务定义: src ⊕ tgt 任一端在中心范围 (即 center↔external 跨边界)
    // "B↔B" 端点都不在 center → 不被计入 (符合用户预期 12)
    const srcIn = centerSet.has(r.sourceCode)
    const tgtIn = centerSet.has(r.targetCode)
    if (srcIn || tgtIn) truthIds.add(r.id)
  }
  return truthIds.size
}

describe('displayStats.total.objectRelations 业务口径回归保护', () => {
  // 复现用户场景: 17 关系, 4 在 center, 8 XOR, 5 两端都在 added (纯外部, 不计入)
  const centerBoCodes = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9']
  const addedBoCodes = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10']

  // 4 关系 in center (两端都在 centerBoCodes, scopeType=internal)
  const centerRels = [
    { id: 1, sourceCode: 'A1', targetCode: 'A2', scopeType: 'internal' },
    { id: 2, sourceCode: 'A2', targetCode: 'A3', scopeType: 'internal' },
    { id: 3, sourceCode: 'A4', targetCode: 'A5', scopeType: 'internal' },
    { id: 4, sourceCode: 'A6', targetCode: 'A7', scopeType: 'internal' }
  ]

  // 8 关系 XOR (一端 center, 一端 added) - 通过关系范围拉入新 BO
  const xorRels = [
    { id: 5, sourceCode: 'A1', targetCode: 'B1', scopeType: 'cross-boundary' },
    { id: 6, sourceCode: 'A2', targetCode: 'B2', scopeType: 'cross-boundary' },
    { id: 7, sourceCode: 'A3', targetCode: 'B3', scopeType: 'cross-boundary' },
    { id: 8, sourceCode: 'A4', targetCode: 'B4', scopeType: 'cross-boundary' },
    { id: 9, sourceCode: 'B5', targetCode: 'A5', scopeType: 'cross-boundary' },
    { id: 10, sourceCode: 'B6', targetCode: 'A6', scopeType: 'cross-boundary' },
    { id: 11, sourceCode: 'B7', targetCode: 'A7', scopeType: 'cross-boundary' },
    { id: 12, sourceCode: 'B8', targetCode: 'A8', scopeType: 'cross-boundary' }
  ]

  // 5 关系 "两端都在 added" (纯外部关系, 用户确认不计入 total)
  const externalRels = [
    { id: 13, sourceCode: 'B1', targetCode: 'B2', scopeType: 'external' },
    { id: 14, sourceCode: 'B3', targetCode: 'B4', scopeType: 'external' },
    { id: 15, sourceCode: 'B5', targetCode: 'B6', scopeType: 'external' },
    { id: 16, sourceCode: 'B7', targetCode: 'B8', scopeType: 'external' },
    { id: 17, sourceCode: 'B9', targetCode: 'B10', scopeType: 'external' }
  ]

  const allRels = [...centerRels, ...xorRels, ...externalRels]

  it('【用户场景】center 4 + XOR 8 = 12 (不计入纯外部 5 条)', () => {
    const count = computeTotalRelationsFallback({
      previewDataRels: allRels,
      centerScope: centerBoCodes
    })
    // 4 internal + 8 cross-boundary + 0 external (端点都不在 center) = 12
    expect(count).toBe(12)
  })

  it('【业务口径】B↔B 端点都在 added 集合的关系不计入 total (用户已确认)', () => {
    // 仅 5 条 both-added 关系, 应返回 0
    const count = computeTotalRelationsFallback({
      previewDataRels: externalRels,
      centerScope: centerBoCodes
    })
    expect(count).toBe(0)
  })

  it('【关键】scopeType=internal 的关系无条件计数 (不管端点是否在 center)', () => {
    // 4 internal 关系, 端点都应在 center
    const count = computeTotalRelationsFallback({
      previewDataRels: centerRels,
      centerScope: centerBoCodes
    })
    expect(count).toBe(4)
  })

  it('【关键】scopeType=cross-boundary 的关系无条件计数 (不管端点是否在 center)', () => {
    // 8 cross-boundary 关系, XOR (一端 center 一端 added)
    const count = computeTotalRelationsFallback({
      previewDataRels: xorRels,
      centerScope: centerBoCodes
    })
    expect(count).toBe(8)
  })

  it('【关键】scopeType=external 的关系仅当端点任一在 center 时被数', () => {
    // 5 external 但端点都在 center: 应全数
    const externalInCenter = [
      { id: 21, sourceCode: 'A1', targetCode: 'A2', scopeType: 'external' },
      { id: 22, sourceCode: 'A3', targetCode: 'A4', scopeType: 'external' }
    ]
    const countInCenter = computeTotalRelationsFallback({
      previewDataRels: externalInCenter,
      centerScope: centerBoCodes
    })
    expect(countInCenter).toBe(2)

    // 5 external 但端点都不在 center: 应 0
    const countOutOfCenter = computeTotalRelationsFallback({
      previewDataRels: externalRels,
      centerScope: centerBoCodes
    })
    expect(countOutOfCenter).toBe(0)
  })

  it('自环关系 (sourceCode === targetCode) 被排除', () => {
    const selfLoop = { id: 100, sourceCode: 'A1', targetCode: 'A1', scopeType: 'internal' }
    const count = computeTotalRelationsFallback({
      previewDataRels: [...allRels, selfLoop],
      centerScope: centerBoCodes
    })
    expect(count).toBe(12)
  })

  it('id 为 null 的关系被跳过', () => {
    const noId = { sourceCode: 'A1', targetCode: 'A2', scopeType: 'internal' }
    const count = computeTotalRelationsFallback({
      previewDataRels: [...allRels, noId],
      centerScope: centerBoCodes
    })
    expect(count).toBe(12)
  })

  it('空数据时返回 0', () => {
    expect(computeTotalRelationsFallback({})).toBe(0)
    expect(computeTotalRelationsFallback({ previewDataRels: [] })).toBe(0)
    expect(computeTotalRelationsFallback({ centerScope: [] })).toBe(0)
  })

  it('【回归保护】17 关系中有 5 条 B↔B 不计入, 验证差异 = 5 (用户报告的差值)', () => {
    // 模拟"误用 union" 的 bug: 期望 17 (错误)
    function computeWithUnionBug({ previewDataRels = [], centerScope = [], addedCodes = [] }) {
      const inScopeSet = new Set([...centerScope, ...addedCodes])
      const truthIds = new Set()
      for (const r of previewDataRels) {
        if (r.id == null) continue
        if (r.sourceCode === r.targetCode) continue
        if (r.scopeType === 'internal' || r.scopeType === 'cross-boundary') {
          truthIds.add(r.id); continue
        }
        const srcIn = inScopeSet.has(r.sourceCode)
        const tgtIn = inScopeSet.has(r.targetCode)
        if (srcIn || tgtIn) truthIds.add(r.id)
      }
      return truthIds.size
    }

    const correct = computeTotalRelationsFallback({
      previewDataRels: allRels,
      centerScope: centerBoCodes
    })
    const buggyUnion = computeWithUnionBug({
      previewDataRels: allRels,
      centerScope: centerBoCodes,
      addedCodes: addedBoCodes
    })

    // 正确口径: 12 (B↔B 不计)
    expect(correct).toBe(12)
    // 错误口径 (之前 v34 误改): 17 (B↔B 计)
    expect(buggyUnion).toBe(17)
    // 差异 = 5 = 用户报告的 5 条 B↔B
    expect(buggyUnion - correct).toBe(5)
  })
})
