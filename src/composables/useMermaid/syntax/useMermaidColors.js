export const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
  warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
  cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
  business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
  nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
}

export function getColors(schemeName) {
  return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
}

export function assignColorsToGroups(uniqueGroups, centerGroupKey, centerDomainColor, colors) {
  const colorMap = new Map()
  let colorIndex = 0

  if (centerGroupKey && uniqueGroups.has(centerGroupKey)) {
    colorMap.set(centerGroupKey, centerDomainColor)
    uniqueGroups.delete(centerGroupKey)
  }

  uniqueGroups.forEach((group) => {
    colorMap.set(group, colors[colorIndex % colors.length])
    colorIndex++
  })

  return colorMap
}

export function getLinkColor(sourceGroupKey, targetGroupKey, centerGroupKey, sourceColor, targetColor) {
  const isSourceCenter = sourceGroupKey === centerGroupKey
  const isTargetCenter = targetGroupKey === centerGroupKey

  if (!isSourceCenter && isTargetCenter) {
    return sourceColor
  } else if (isSourceCenter && !isTargetCenter) {
    return targetColor
  } else {
    return sourceColor || targetColor || '#333333'
  }
}
