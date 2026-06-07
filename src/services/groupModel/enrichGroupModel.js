import { isTerminalGroup } from './types.js'

export function enrichGroupModel(groupModel, chartType, options) {
  const { colorMap, containerColorMap, centerCodes, annotationMap, nodeTextColor } = options

  const flattenedGroups = groupModel.getFlattenedGroups()
  
  flattenedGroups.forEach(group => {
    const isTerminal = isTerminalGroup(group, chartType)

    if (isTerminal) {
      const code = group.elementRef?.code
      if (code) {
        group.color = colorMap?.get(code) || null
        group.textColor = nodeTextColor || 'black'
        group.isCenter = centerCodes?.has(code) || false
        const annotation = annotationMap?.get(code)
        if (annotation) {
          group.annotationCategory = annotation.category || 'info'
          group.annotationContent = annotation.content || ''
        }
      }
    } else {
      if (containerColorMap) {
        group.color = containerColorMap.get(group.id) || containerColorMap.get(group.elementRef?.code) || null
      }
    }
  })
}
