// [FIX 2026-07-22] 层级节点 icon 映射 (独立文件, 供 HierarchicalTreePicker 和未来的 ObjectScopeSection 共用)
// 原本硬编码在 ObjectScopeSection.vue, 现抽出便于共享
import { Box, Document, Folder, FolderOpened, Connection } from '@element-plus/icons-vue'

/**
 * 层级节点 type → Element Plus icon 组件映射
 *
 * 命名约定:
 *   - product:          顶层产品 (Box)
 *   - version:          版本 (Folder)
 *   - domain:           领域 (FolderOpened)
 *   - sub_domain:       子领域 (Document)
 *   - service_module:   服务模块 (保留以备扩展)
 *   - business_object:  业务对象 (保留以备扩展)
 *   - default:          未知类型 fallback (Connection)
 */
export const HIERARCHY_ICON_MAP = {
  product: Box,
  version: Folder,
  domain: FolderOpened,
  sub_domain: Document,
  service_module: Document,
  business_object: Box,
  default: Connection,
}

/**
 * 根据 type name 查找 icon 组件
 * @param {string} typeName - 节点 type (如 'product', 'sub_domain')
 * @returns {Component|null} Element Plus icon 组件
 */
export function getNodeIcon(typeName) {
  return HIERARCHY_ICON_MAP[typeName] || HIERARCHY_ICON_MAP.default
}