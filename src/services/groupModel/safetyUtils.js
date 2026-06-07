/**
 * 安全工具模块
 * 为递归调用提供保护机制，防止死循环和无限递归
 */

export const MAX_RECURSION_DEPTH = 20

export function createVisitedSet() {
  return new Set()
}

export function checkDepth(depth, context = 'Unknown') {
  if (depth > MAX_RECURSION_DEPTH) {
    console.warn(`[${context}] Max recursion depth exceeded: ${depth}`)
    return false
  }
  return true
}

export function checkCycle(id, visited, context = 'Unknown') {
  if (visited.has(id)) {
    console.warn(`[${context}] Cycle detected for id: ${id}`)
    return true
  }
  visited.add(id)
  return false
}

export function createRecursionGuard(context = 'Unknown') {
  let depth = 0
  const visited = new Set()
  
  return {
    enter(id) {
      if (!checkDepth(depth, context)) {
        return false
      }
      if (id && checkCycle(id, visited, context)) {
        return false
      }
      depth++
      return true
    },
    exit() {
      depth--
    },
    getDepth() {
      return depth
    },
    getVisited() {
      return visited
    }
  }
}
