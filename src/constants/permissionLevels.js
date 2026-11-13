/**
 * 权限级别常量定义
 * 
 * 单一事实源：所有权限级别枚举统一定义在此文件
 * 与后端 permission_rule 表的 permission_level 字段保持一致
 */

// TODO-1 [2026-11-13] D-1 决策：manage 权限等级的归一本轮不处理。
// 后端 meta_enum_api.PERMISSION_LEVELS 为 none/read/write/admin，本文件保留 manage
// 以兼容历史数据；后续统一时再删除本文件并全部改读 /api/v2/meta/enums/permission_level。
export const PERMISSION_LEVELS = [
  { value: 'none', label: '无权限' },
  { value: 'read', label: '只读' },
  { value: 'write', label: '读写' },
  { value: 'admin', label: '完全管理' }
]

export const PERMISSION_LEVEL_VALUES = PERMISSION_LEVELS.map(level => level.value)

export const PERMISSION_LEVEL_LABELS = {
  none: '无权限',
  read: '只读',
  write: '读写',
  admin: '完全管理'
}

export function getPermissionLevelLabel(value) {
  return PERMISSION_LEVEL_LABELS[value] || value
}

export function getPermissionLevelByValue(value) {
  return PERMISSION_LEVELS.find(level => level.value === value)
}

export default PERMISSION_LEVELS
