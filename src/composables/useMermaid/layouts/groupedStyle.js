/**
 * 生成分组样式代码
 */
export function generateGroupStyle(group, groupId) {
  if (!group || !group.layout) {
    return `style ${groupId} fill:#f5f5f5,stroke:#333333,stroke-width:1px\n`
  }

  if (group.layout.visible === false) {
    return `style ${groupId} fill:none,stroke:none\n`
  }

  const style = group.layout.style || {}
  const fill = style.fill || '#f5f5f5'
  const stroke = style.stroke || '#333333'
  const strokeWidth = style.strokeWidth !== undefined ? style.strokeWidth : 1
  const strokeDasharray = style.strokeDasharray || ''

  let styleCode = `style ${groupId} fill:${fill},stroke:${stroke},stroke-width:${strokeWidth}px`

  if (strokeDasharray) {
    styleCode += `,stroke-dasharray:${strokeDasharray}`
  }

  styleCode += '\n'

  return styleCode
}
