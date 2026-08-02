import { COLOR_SCHEMES } from '@/constants/diagram'

export { COLOR_SCHEMES }

export function getColors(schemeName) {
  return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
}

export function assignColorsToGroups(uniqueGroups, colors, customColors = {}) {
  const colorMap = new Map()
  let colorIndex = 0

  uniqueGroups.forEach((group) => {
    if (customColors[group]) {
      colorMap.set(group, customColors[group])
    } else {
      colorMap.set(group, colors[colorIndex % colors.length])
      colorIndex++
    }
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
