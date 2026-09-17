// [REFACTOR 2026-07-22] icon name string -> Element Plus icon component
// 仅负责"图标名 → 组件"的桥接, 不包含任何业务层 type -> icon 的映射
// 业务映射由后端从 hierarchies.yaml 的 levels[].ui.icon 读取, 经 API 响应传到前端
import * as ElIcons from '@element-plus/icons-vue'

/**
 * 默认 fallback icon (无匹配时使用)
 */
export const FALLBACK_ICON_NAME = 'Connection'

/**
 * 把 icon name string (YAML 中 ui.icon 字段, 如 "account_tree") 转成 Element Plus icon 组件
 *
 * 命名空间转换:
 *   - snake_case (YAML/MDI 风格)  -> PascalCase (Element Plus 导出)
 *   - 例如: account_tree -> AccountTree
 *
 * @param {string|null|undefined} name - icon name from YAML ui.icon
 * @returns {Component|null} Element Plus icon component, or null if name is empty
 */
export function resolveIcon(name) {
  if (!name || typeof name !== 'string') return null
  const pascal = name
    .split(/[_-]/)
    .filter(Boolean)
    .map(s => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase())
    .join('')
  // 优先用 PascalCase 查表, 否则 fallback 到原 name
  return ElIcons[pascal] || ElIcons[name] || null
}

/**
 * [向后兼容] 旧 API: 给 type name (业务层 type) 返回 icon 组件
 * 用途: 旧调用方仍传 type 时, 我们尝试: type name -> snake_case -> 查表
 * 注意: 不维护硬编码映射, 依赖 resolveIcon 的命名空间转换
 *
 * @deprecated 推荐从 API 响应中的 n.icon (YAML ui.icon) 直接 resolveIcon
 * @param {string} typeName - 节点 type (如 'product', 'sub_domain')
 */
export function getNodeIcon(typeName) {
  if (!typeName) return resolveIcon(FALLBACK_ICON_NAME)
  // 尝试多种命名空间转换
  return resolveIcon(typeName)
    || resolveIcon(typeName.replace(/_/g, '-'))
    || resolveIcon(FALLBACK_ICON_NAME)
}