/**
 * 权限相关常量定义
 * 集中管理 UI 文本，便于维护和国际化迁移
 */

// ==================== 权限来源（source） ====================

/**
 * 权限来源类型
 * - auto: 菜单自动派生
 * - include: 手动包含（grant）
 * - exclude: 手动排除（deny）
 * - '': 未分配
 */
export type PermissionSource = 'auto' | 'include' | 'exclude' | ''

/**
 * 权限来源标签（UI 显示文本）
 */
export const SOURCE_LABELS = {
  auto: '自动',
  include: '包含',
  exclude: '排除',
  none: '未分配',
} as const

/**
 * 权限来源 i18n key（用于国际化迁移）
 */
export const SOURCE_I18N_KEYS = {
  auto: 'permission.source.auto',
  include: 'permission.source.include',
  exclude: 'permission.source.exclude',
  none: 'permission.source.none',
} as const

/**
 * 获取权限来源标签
 */
export function getSourceLabel(source: PermissionSource | 'none'): string {
  return SOURCE_LABELS[source] || ''
}

// ==================== 动作分组（action groups） ====================

/**
 * 动作分组类型
 */
export type ActionGroupKey = 'view' | 'edit' | 'manage'

/**
 * 动作分组标签
 */
export const GROUP_LABELS = {
  view: '查看',
  edit: '编辑',
  manage: '管理',
} as const

/**
 * 动作分组 i18n keys
 */
export const GROUP_I18N_KEYS = {
  view: 'permission.group.view',
  edit: 'permission.group.edit',
  manage: 'permission.group.manage',
} as const

/**
 * 动作分组层级依赖
 */
export const GROUP_DEPENDENCIES = {
  manage: ['edit'],
  edit: ['view'],
  view: [],
} as const

// ==================== 动作分组到 actions 映射 ====================

/**
 * 动作分组包含的 actions
 */
export const GROUP_ACTIONS_MAP = {
  view: ['read', 'list'],
  edit: ['read', 'list', 'create', 'update'],
  manage: ['read', 'list', 'create', 'update', 'delete'],
} as const

// ==================== 独立动作（standalone actions） ====================

/**
 * 独立动作定义
 */
export const STANDALONE_ACTIONS = {
  export: { label: '导出', description: '独立权限，不隐含 read' },
  import: { label: '导入', description: '独立权限，不隐含 create' },
  assign: { label: '分配', description: '关联操作（成员管理）' },
  unassign: { label: '取消分配', description: '关联操作（成员管理）' },
  associate: { label: '关联', description: '关联操作（关系建立）' },
  dissociate: { label: '取消关联', description: '关联操作（关系解除）' },
  grant: { label: '授权', description: '关联操作（权限授予）' },
  revoke: { label: '撤销', description: '关联操作（权限撤销）' },
} as const

// ==================== UI 区域标题 ====================

/**
 * UI 区域标题
 */
export const SECTION_TITLES = {
  actionGroups: '功能权限',
  detailedPermissions: '详细权限',
  dataScope: '数据约束',
  dataScopeHint: '建议为此菜单配置',
} as const

// ==================== Badge 文本 ====================

/**
 * Badge 标签文本
 */
export const BADGE_LABELS = {
  capability: '权限',
  hasDataScope: '有数据范围',
  denied: '禁止',
} as const
