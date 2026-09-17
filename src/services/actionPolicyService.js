/**
 * actionPolicyService - 行级动作策略引擎 (前端)
 *
 * [P1-B 2026-07-25] 替代分散在以下位置的硬编码状态判断:
 *   - MetaListPage.vue#canDelete (is_system / system_value 检查)
 *   - metaTransformService.js#filterRowActions (_isNew / category=system /
 *     rowMutability 检查)
 *   - useFieldPolicy.js#evaluateMutability (is_system 检查)
 *
 * 设计对齐: 后端 meta/services/action_policy.py 的 ActionPolicy 类
 *   - 后端基于 meta_object.semantics.mutability 做"对象级"过滤 (locked/extensible/fullEditable)
 *   - 前端在此基础上增加"行级"规则 (is_system / _isNew / category=system)
 *
 * 返回值约定:
 *   { allowed: boolean, reason: string }
 *   - allowed=true 时 reason 为空字符串
 *   - allowed=false 时 reason 给出可读的拒绝原因 (可用于 tooltip)
 *
 * @module services/actionPolicyService
 */

/**
 * Action key 别名归一化
 *   - 'edit' / 'update' / 'modify' → 'edit'
 *   - 'create' / 'new' / 'add' / '新建' → 'create'
 *   - 'delete' / 'remove' / 'drop' → 'delete'
 *   - 'view' / 'read' / 'detail' → 'view'
 *   - 其他原样返回 (lowercase)
 */
const ACTION_ALIASES = {
  edit: ['edit', 'update', 'modify'],
  create: ['create', 'new', 'add', '新建'],
  delete: ['delete', 'remove', 'drop'],
  view: ['view', 'read', 'detail'],
}

/**
 * 归一化 action.key 为 canonical key
 * @param {Object|string} action - action 配置对象或 action key 字符串
 * @returns {string} canonical key ('edit' | 'create' | 'delete' | 'view' | 原值 lowercase)
 */
export function normalizeActionKey(action) {
  const raw = typeof action === 'string' ? action : (action?.key || '')
  const key = String(raw).toLowerCase()
  for (const [canonical, aliases] of Object.entries(ACTION_ALIASES)) {
    if (aliases.includes(key)) return canonical
  }
  return key
}

/**
 * 检查是否是新增未保存行
 *   - _isNew === true
 *   - id 是字符串且以 '__new_' 开头 (前端临时 ID)
 */
export function isNewRow(row) {
  if (!row) return false
  if (row._isNew === true) return true
  if (typeof row.id === 'string' && row.id.startsWith('__new_')) return true
  return false
}

/**
 * 检查是否是系统内置行 (不可改删)
 *   - is_system === true
 *   - system_value === true
 */
export function isSystemRow(row) {
  return row?.is_system === true || row?.system_value === true
}

/**
 * 检查是否允许对某行执行某操作
 *
 * 规则优先级 (按评估顺序):
 *   1. 新增行 (_isNew): 禁 edit/delete (走本地路径, 不调后端)
 *   2. enum_type + category=system: 禁 edit/delete (系统内置枚举)
 *   3. rowMutability=locked: 禁 edit/delete (对象级锁定)
 *   4. rowMutability=extensible: 禁 edit; delete 仅允许非系统行
 *   5. rowMutability=fullEditable 或 null: 全部允许 (默认)
 *
 * 注: create 不在行级过滤范围内 (create 是 toolbar 级, 由 canPerformCrud 控制)
 *
 * @param {Object} action - action 配置 ({ key, ... }) 或 action key 字符串
 * @param {Object} row - 行数据
 * @param {Object} [ctx] - 上下文
 * @param {string} [ctx.objectType] - 对象类型 (如 'enum_type')
 * @param {string} [ctx.rowMutability] - 行可维护性 ('locked'|'extensible'|'fullEditable'|null)
 * @returns {{ allowed: boolean, reason: string }}
 */
export function canPerformAction(action, row, ctx = {}) {
  const actionKey = normalizeActionKey(action)
  const { objectType, rowMutability } = ctx

  // 规则 1: 新增行不能 edit/delete (走本地路径, 不调后端)
  if (isNewRow(row) && (actionKey === 'edit' || actionKey === 'delete')) {
    return { allowed: false, reason: '新增行未保存,不可走后端操作' }
  }

  // 规则 2: 系统内置 enum_type 不可改删
  if (objectType === 'enum_type' && row?.category === 'system'
      && (actionKey === 'edit' || actionKey === 'delete')) {
    return { allowed: false, reason: '系统内置枚举不可修改/删除' }
  }

  // 规则 3: rowMutability=locked → edit/delete 禁 (create 由 toolbar 层控制)
  if (rowMutability === 'locked'
      && (actionKey === 'edit' || actionKey === 'delete')) {
    return { allowed: false, reason: '该对象已锁定,不可编辑/删除' }
  }

  // 规则 4: rowMutability=extensible
  if (rowMutability === 'extensible') {
    if (actionKey === 'edit') {
      return { allowed: false, reason: '该对象为可扩展模式,不可编辑现有字段' }
    }
    if (actionKey === 'delete' && isSystemRow(row)) {
      return { allowed: false, reason: '系统内置行不可删除' }
    }
  }

  // 默认允许
  return { allowed: true, reason: '' }
}

/**
 * 批量过滤行操作 (替代 metaTransformService.filterRowActions 的硬编码块)
 *
 * 此函数仅处理"行级状态规则",不处理:
 *   - 权限检查 (checkPermission) - 由调用方先处理
 *   - 自定义 condition (evaluateCondition) - 由调用方先处理
 *
 * @param {Array} actions - action 配置数组
 * @param {Object} row - 当前行数据
 * @param {Object} ctx - 上下文 { objectType, rowMutability }
 * @returns {Array} 过滤后的 actions
 */
export function filterByRowPolicy(actions, row, ctx = {}) {
  if (!Array.isArray(actions)) return []
  return actions.filter(action => canPerformAction(action, row, ctx).allowed)
}

export default {
  normalizeActionKey,
  isNewRow,
  isSystemRow,
  canPerformAction,
  filterByRowPolicy,
}
