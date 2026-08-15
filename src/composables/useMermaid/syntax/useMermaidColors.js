import { COLOR_SCHEMES } from '@/constants/diagram'

export { COLOR_SCHEMES }

export function getColors(schemeName) {
  return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
}

// [FIX 2026-08-11 colorIndex-drift] 改为按位置索引分配默认色, 而非"跳过自定义色"计数器.
//   根因: 旧实现 colorIndex 只对非自定义色分组递增. 当某分组 (如 供应链云) 设了自定义色,
//   它不再消耗 colorIndex → 后续分组 (如 制作云) 默认色索引整体前移
//   (制作云 从 colors[1]=绿 变成 colors[0]=蓝). 用户改一个分组色, 其它分组颜色跟着漂移.
//   修复: 默认色 = colors[分组在 uniqueGroups 中的位置 % len], 与自定义色无关 →
//   改某分组自定义色不再影响其它分组默认色. 位置索引在结构不变时是稳定的.
export function assignColorsToGroups(uniqueGroups, colors, customColors = {}) {
  const colorMap = new Map()

  Array.from(uniqueGroups).forEach((group, idx) => {
    colorMap.set(group, customColors[group] || colors[idx % colors.length])
  })

  return colorMap
}

// [FIX 2026-08-02 v6] getLinkColor 增加中心范围选项 (向后兼容):
//   options.isSourceCenter / isTargetCenter / centerScopeColor
//   规则:
//   1. 双中心 -> centerScopeColor 灰 (与中心节点灰色一致)
//   2. 一中心一非中心 -> 非中心节点的颜色
//   3. 双非中心 或 不区分中心范围 -> 黑色
export function getLinkColor(sourceGroupKey, targetGroupKey, sourceColor, targetColor, options = {}) {
  const { isSourceCenter = false, isTargetCenter = false, centerScopeColor = '#333333' } = options
  if (isSourceCenter && isTargetCenter) {
    return centerScopeColor
  }
  if (isSourceCenter) {
    return targetColor || sourceColor || '#333333'
  }
  if (isTargetCenter) {
    return sourceColor || targetColor || '#333333'
  }
  return '#000000'
}
