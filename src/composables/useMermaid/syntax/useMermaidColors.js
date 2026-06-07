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

export function getLinkColor(sourceGroupKey, targetGroupKey, sourceColor, targetColor) {
  return sourceColor || targetColor || '#333333'
}
