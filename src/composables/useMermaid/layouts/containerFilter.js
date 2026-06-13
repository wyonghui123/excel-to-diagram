/**
 * 容器过滤器 (v32 复盘修复 - 2026-06-11)
 *
 * 背景: 4 个 layout (grouped/linear/zone/grid) 中, 只有 grouped 检查 container.enabled,
 *       linear/zone 不检查, 导致 disabled 容器在某些 layout 下仍渲染
 *
 * 修复: 抽 filterEnabledContainers 前置, 4 个 layout 统一调用
 *
 * 注意:
 * - 此函数不修改原数组, 返回新数组
 * - null/undefined 容器会被过滤
 * - container.enabled !== false 的都保留 (默认 true)
 */

/**
 * 过滤禁用的容器
 * @param {Array} containers - 原始容器数组
 * @returns {Array} 过滤后的容器数组
 */
export function filterEnabledContainers(containers) {
  if (!containers || containers.length === 0) {
    return []
  }
  return containers.filter(c => c && c.enabled !== false)
}

/**
 * 过滤并记录被禁用的容器 (供调试/日志)
 * @param {Array} containers - 原始容器数组
 * @returns {{enabled: Array, disabled: Array}}
 */
export function partitionContainersByEnabled(containers) {
  if (!containers || containers.length === 0) {
    return { enabled: [], disabled: [] }
  }
  const enabled = []
  const disabled = []
  containers.forEach(c => {
    if (!c) return
    if (c.enabled === false) {
      disabled.push(c)
    } else {
      enabled.push(c)
    }
  })
  return { enabled, disabled }
}
