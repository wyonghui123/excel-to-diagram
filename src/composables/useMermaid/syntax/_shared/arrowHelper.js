/**
 * @file arrowHelper.js
 * @description 关系箭头生成辅助函数（v1.5 双向支持 - 修复 2026-06-15）
 *
 * 触发条件：link.relationDirection === 'BIDIRECTIONAL' → 输出 `<-->` 双箭头
 *            其它值（'PUSH'/'PULL'/'双向'/''/undefined）→ 输出 `-->` 单箭头
 *
 * ⚠️ 数据流修正（来自架构数据管理页 → 图表）：
 *   数据库 (relationship.relation_direction) 存储的值为 enum code，不是中文名:
 *     - 'PUSH'        → '推'  (单向)
 *     - 'PULL'        → '拉'  (单向)
 *     - 'BIDIRECTIONAL' → '双向' (双向)  ← 关键
 *   修复历史：
 *     v1.4: 误用 '双向' (中文) → 数据库中实际为 'BIDIRECTIONAL' (英文 code)
 *           双向判断永远 false → 所有关系都渲染为 --> 单向
 *     v1.5: 改用 'BIDIRECTIONAL' 作为权威匹配 (数据库 enum code)
 *           同时保留 '双向' 作为 fallback 兼容历史中文数据
 *
 * 用法：
 *   import { getArrowSyntax, sanitizeLabel } from './_shared/arrowHelper.js'
 *   mermaidCode += getArrowSyntax(sourceId, targetId, label, link)
 */

/**
 * 关系箭头生成（核心函数）
 *
 * @param {string} sourceId - 源节点 ID
 * @param {string} targetId - 目标节点 ID
 * @param {string} label - 关系码/描述（可空）
 * @param {Object} link - 完整 link 对象（必须含 relationDirection?: string）
 * @returns {string} mermaid 语法片段（含缩进 + 换行）
 */
export function getArrowSyntax(sourceId, targetId, label, link) {
  // v1.5: 用 isBidirectionalLink() 统一判断 (兼容 BIDIRECTIONAL 和 双向 两种值)
  const isBidi = isBidirectionalLink(link)
  const safeLabel = sanitizeLabel(label)
  const labelPart = safeLabel ? ` ${safeLabel} ` : ''

  if (isBidi) {
    // 双向 (Mermaid 11 官方语法):
    //   - 无 label: A <--> B
    //   - 有 label: A <-- text --> B   (注意: <--|"label"|--> 不是合法语法)
    return labelPart
      ? `  ${sourceId} <--${labelPart}--> ${targetId}\n`
      : `  ${sourceId} <--> ${targetId}\n`
  }
  // 单向 (Mermaid 11 标准):
  //   - 无 label: A --> B
  //   - 有 label: A -->|"label"| B   (官方支持的 |"text"| 内联语法)
  return labelPart
    ? `  ${sourceId} -->|"${safeLabel}"| ${targetId}\n`
    : `  ${sourceId} --> ${targetId}\n`
}

/**
 * label 转义（与现有 useBusinessObjectSyntax L891-908 / L1062-1074 保持一致）
 * - | → /
 * - 换行 → 空格
 * - " → '
 * - 前后空白 trim
 */
export function sanitizeLabel(label) {
  if (!label) return ''
  const raw = String(label).trim()
  if (!raw) return ''
  return raw
    .replace(/\|/g, '/')
    .replace(/[\r\n]+/g, ' ')
    .replace(/"/g, "'")
    .trim()
}

/**
 * 判断 link 是否双向（供 fixArrowMarkers / addBidirectionalAttributes 等调用方使用）
 *
 * 数据库 enum code 是 'BIDIRECTIONAL' (英文)，不是 '双向' (中文)。
 * 之前的 v1.4 用 === '双向' 永远 false，所有关系都退化为 --> 单向。
 * 修复 (v1.5): 用 'BIDIRECTIONAL' 作为权威匹配，同时兼容旧的 '双向' (历史数据/直接测试)。
 *
 * @param {Object} link - 完整 link 对象
 * @returns {boolean} true 表示双向，false 表示单向
 */
export function isBidirectionalLink(link) {
  if (!link) return false
  const dir = link.relationDirection
  return dir === 'BIDIRECTIONAL' || dir === '双向'
}
