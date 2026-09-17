/**
 * 权限相关常量定义
 * 集中管理 UI 文本，便于维护和国际化迁移
 */

// ==================== 权限来源（source） ====================

/**
 * 权限来源类型
 * - auto: 跟随菜单（自动联动：勾选菜单自动授予，取消菜单联动清除）
 * - include: 单独授予（独立生效：不随菜单勾选变化）
 * - exclude: 手动排除（deny）
 * - '': 未分配（不显示来源标签）
 * [REFACTOR 2026-08-28 v68] 参考 SAP PFCG / AWS IAM 的来源语义：
 *   标识回答两个问题——权限从哪来 + 改父级时是否联动
 */
export type PermissionSource = 'auto' | 'include' | 'exclude' | ''

/**
 * 权限来源标签（UI 显示文本）
 * none 为空字符串：未分配菜单不显示来源标签
 */
export const SOURCE_LABELS = {
  auto: '跟随菜单',
  include: '单独授予',
  exclude: '排除',
  none: '',
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

// ==================== 权限数据模型（单一事实源） ====================
// [2026-08-28 重构清理] 原 useMenuPermission.ts 与 MenuPermissionMatrix.vue
// 各维护一份同名 interface（字段漂移无编译保护），统一收敛到此处。
// 字段与后端 role_menu_api._build_role_unified_data 的返回结构对齐。

/** 单条功能权限（required_permissions 数组项） */
export interface Permission {
  code: string
  label: string
  granted: boolean
  source: PermissionSource
}

/** 数据范围（菜单级 data_scopes 数组项） */
export interface DataScope {
  resource_type: string
  permissions: Array<{ level: string }>
}

/** 动作分组（view/edit/manage）实时状态 */
export interface ActionGroupState {
  granted: boolean
  source: PermissionSource
}

/** 独立动作（export/import/assign 等，不参与分组） */
export interface StandalonePerm {
  action: string
  label: string
  granted: boolean
  source: PermissionSource
}

/** BO 维度的权限分组（bo_permission_groups 数组项，由后端 _derive_bo_permission_groups 推导） */
export interface BoPermissionGroup {
  bo_id: string
  bo_name: string
  groups: Record<string, ActionGroupState>
  standalone: StandalonePerm[]
}

/** 菜单的 BO 绑定声明（menus.bo_bindings JSON 字段） */
export interface BoBinding {
  bo_id: string
  role: 'primary' | 'secondary' | 'reference'
  include_actions?: string[]
}

/** 菜单权限模型（unified-permissions 接口的菜单项，含树形 children） */
export interface Menu {
  menu_code: string
  display_name: string
  menu_path: string
  assigned: boolean
  has_data_scope: boolean
  required_permissions: Permission[]
  bo_permission_groups?: BoPermissionGroup[]
  data_scopes?: DataScope[]
  data_permission_hint?: { resource_types: string[] }
  bo_bindings?: BoBinding[]
  parent_menu?: string
  primary_object_type?: string
  object_types?: string[]
  auto_generated?: boolean
  children?: Menu[]
}

// ==================== ResourceActionMatrix 类型（T-P1-3-C 2026-09-16 迁移） ====================
// [2026-09-16 重构清理] ResourceActionMatrix.vue 由 JS 迁移至 TS,
//   原 14 个 defineProps + 4 个 defineEmits 类型化收敛到此文件，避免类型定义散落组件内部。
//   内部 ref/computed/function 保持 JS（收益不抵成本），仅顶层 props/emits 类型化。

/** 动作类型标签（列头 [CRUD/批量/业务] 分组前缀） */
export type ActionType = 'crud' | 'batch' | 'business'

/** 动作元数据（action_id → {action_type, name, yaml_id}） */
export interface ActionMetaItem {
  action_type?: ActionType
  name?: string
  yaml_id?: string
}

/** 矩阵单元格（granted + 来源语义） */
export interface MatrixCell {
  granted: boolean
  source: PermissionSource
}

/** 矩阵行（resource_type + 字段 + cells） */
export interface MatrixRow {
  resource_type: string
  label?: string
  ps_names?: string[]
  row_scope?: Record<string, unknown>
  ps_ids?: number[]
  cells: Record<string, MatrixCell>
  [key: string]: unknown  // 允许额外字段（如 row.ps_names 预览用）
}

/** 矩阵整体结构（role_resource_action_matrix） */
export interface MatrixPayload {
  permission_set_id?: number | string
  columns: string[]
  resources: MatrixRow[]
}

/** 范围矩阵条目（resource_type → dimension_id → scope） */
export interface ScopeMatrixEntry {
  scope_mode?: 'all' | 'include' | 'exclude'
  dimension_values?: Array<string | number | { id: string | number; code?: string; name?: string }>
  __expression?: string
  __expression_display?: string
  __scope_value_names?: string[]
  __anchor_codes?: string[]
  __hit_count?: number
  [key: string]: unknown
}

/** 维度元数据（来自 meta.normalizedForDimensionSelector） */
export interface DimensionItem {
  id: string
  name: string
  [key: string]: unknown
}

/** 当前选中菜单对象（contextMenu prop） */
export interface ContextMenu {
  menu_code: string
  display_name?: string
  [key: string]: unknown
}

/** 资源层级（resource_type → { parent, level, kind }，用于 el-table 树形） */
export interface ResourceHierarchyEntry {
  parent?: string
  level?: number
  kind?: string
  [key: string]: unknown
}

/** 资源类型标签（resource_type → 中文名） */
export type ResourceTypeLabels = Record<string, string>

/** 动作标签（action → 中文名） */
export type ActionLabels = Record<string, string>

/** 动作灰化原因（resource_type → action → 说明） */
export type ActionHints = Record<string, Record<string, string>>

/** resource_action_matrix（resource_type → 可授权动作列表） */
export type SupportedActionsMap = Record<string, string[]>

/** 外部资源类型筛选 */
export type ExternalResourceFilters = string[]

/** 外部筛选模式 */
export type ExternalResourceFilterMode = 'sync' | 'allowlist'

/** 范围矩阵整体结构（resource_type → dimension_id → scope） */
export type ScopeMatrix = Record<string, Record<string, ScopeMatrixEntry>>

/** ResourceActionMatrix emit 事件契约 */
export interface ResourceActionMatrixEmits {
  /** 单元格勾选状态变更（保存链路） */
  (e: 'change', changes: Array<{ resource_type: string; action: string; granted: boolean; source: PermissionSource }>): void
  /** 范围矩阵变更（dimension_scope 编辑） */
  (e: 'scope-change', newMatrix: ScopeMatrix): void
  /** 打开条件规则对话框 */
  (e: 'open-condition-dialog', payload: unknown): void
  /** 清除当前上下文菜单 */
  (e: 'clear-context'): void
}
