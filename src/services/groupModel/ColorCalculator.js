const COLOR_SCHEMES = {
  default: ['#1890FF', '#2FC25B', '#FACC14', '#223273', '#8543E0', '#13C2C2', '#3436C7', '#F04864'],
  vibrant: ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16', '#E86452', '#6DC8EC', '#945FB9', '#FF9845'],
  pastel: ['#A0C4FF', '#B5EAD7', '#FFDAC1', '#C7CEEA', '#E2F0CB', '#FFB7B2', '#FFFFD8', '#D5A6BD'],
  warm: ['#FF6B6B', '#FFA07A', '#FFD93D', '#6BCB77', '#4D96FF', '#9B59B6', '#E17055', '#00B894'],
  cool: ['#74B9FF', '#81ECEC', '#55EFC4', '#A29BFE', '#DFE6E9', '#00CEC9', '#6C5CE7', '#0984E3'],
  business: ['#2C3E50', '#3498DB', '#1ABC9C', '#E67E22', '#9B59B6', '#E74C3C', '#F39C12', '#27AE60'],
  nature: ['#2D6A4F', '#40916C', '#52B788', '#74C69D', '#95D5B2', '#B7E4C7', '#D8F3DC', '#1B4332']
}

export class ColorCalculator {
  static compute(config) {
    const { nodes, colorGroupBy, colorScheme, centerScopeColor, customColors, centerScopeHighlight = true } = config
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
      groupColorMap.set(group, (customColors && customColors[group]) || colors[index % colors.length])
    })

    nodes.forEach(node => {
      const groupKey = groupKeys.get(node.code)
      const baseColor = groupColorMap.get(groupKey) || colors[0]
      const finalColor = (centerScopeHighlight && node.isCenter) ? centerScopeColor : baseColor
      colorMap.set(node.code, finalColor)
    })

    return { colorMap, groupColorMap }
  }
}
