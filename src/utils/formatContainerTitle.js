/**
 * 格式化容器标题，在长标题中添加换行符
 * 优化策略：
 * 1. 主名称与括号内容分行
 * 2. 括号内容保持在一行
 * @param {string} title - 原始标题
 * @param {number} maxLength - 每行最大字符数（用于超长无括号标题）
 * @returns {string} 格式化后的标题
 */
export function formatContainerTitle(title, maxLength = 12) {
  if (!title) {
    return title
  }

  // 检测括号格式：主名称（路径1 / 路径2 / ...）
  const bracketMatch = title.match(/^(.+?)[（(](.+)[）)]$/)
  if (bracketMatch) {
    const mainPart = bracketMatch[1].trim()
    const pathPart = bracketMatch[2].trim()
    
    // 主名称一行，括号内容整体一行
    return `${mainPart}\n（${pathPart}）`
  }

  // 无括号的标题：检查是否有 / 分隔
  if (title.includes(' / ')) {
    return title.replace(/\s*\/\s*/g, '\n')
  }

  // 超长标题按字符数分行
  if (title.length > maxLength) {
    const lines = []
    let currentLine = ''

    for (const char of title) {
      if (currentLine.length >= maxLength && char !== ' ') {
        lines.push(currentLine)
        currentLine = char
      } else {
        currentLine += char
      }
    }

    if (currentLine) {
      lines.push(currentLine)
    }

    return lines.join('\n')
  }

  return title
}
