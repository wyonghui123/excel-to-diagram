/**
 * auditLogFormat.js - 操作日志字段业务化工具
 *
 * 业务人员视角: 把后端技术字段翻译为业务术语
 * - object_type: 模型名 → 业务术语 (如 annotation → 备注)
 * - action: 内部 action → 业务动作 (如 DELETE_BLOCKED → 删除已阻止)
 * - user_name: system → 系统
 *
 * 单一事实源: 这里集中管理所有翻译 map, 列表页 + 详情弹窗共用
 *
 * @module utils/auditLogFormat
 */

/**
 * object_type → 业务名 翻译表
 *
 * 来源: yaml schema 的 name 字段 (meta/schemas/*.yaml)
 * 优先级: useHierarchyTypes.getLabel (运行时) > 此表 (静态回退)
 */
export const OBJECT_TYPE_LABELS = {
  // 主层级
  product: '产品',
  version: '版本',
  domain: '领域',
  sub_domain: '子领域',
  service_module: '服务模块',
  business_object: '业务对象',
  // 关联
  relationship: '业务关系',
  // 权限
  permission: '权限',
  permission_rule: '权限规则',
  permission_bundle: '权限包',
  role: '角色',
  role_menu: '角色菜单',
  role_permissions: '角色权限',
  role_dimension_scope: '角色数据范围',
  role_data_permission: '角色数据权限',
  // 用户
  user: '用户',
  user_group: '用户组',
  user_group_member: '用户组成员',
  // 菜单
  menu: '菜单',
  menu_permission: '菜单权限',
  // 枚举
  enum_type: '枚举类型',
  enum_value: '枚举值',
  // 业务
  employee_data_scope: '员工数据范围',
  // 任务
  scheduled_task: '定时任务',
  task_queue: '任务队列',
  ai_async_task: 'AI 异步任务',
  subflow: '子流程',
  // 元数据
  annotation: '备注',
  // 测试/内部
  test_objects: '测试对象',
  __audit_failure__: '审计异常',
  _unknown: '未识别操作'
}

/**
 * action → 业务动作 翻译表
 *
 * 列表 + 详情都依赖此翻译
 * 优先级: 业务动作 > 系统动作 (运维类归为系统)
 */
export const ACTION_LABELS = {
  // 业务 CRUD
  CREATE: '创建',
  UPDATE: '更新',
  DELETE: '删除',
  DELETE_BLOCKED: '删除已阻止',
  READ: '查看',
  RESTORE: '恢复',
  EXECUTE: '执行',

  // 业务关联
  ASSOCIATE: '添加关联',
  DISSOCIATE: '移除关联',
  ASSIGN: '分配',
  UNASSIGN: '取消分配',
  REVOKE: '撤销',

  // 批量
  BATCH_CREATE: '批量创建',
  BATCH_UPDATE: '批量更新',
  BATCH_DELETE: '批量删除',
  BATCH_ASSIGN: '批量分配',
  BATCH_UNASSIGN: '批量取消',

  // 业务流
  SUBFLOW: '执行子流程',
  SYNC: '数据同步',
  DATA_SYNC: '数据同步',
  EXPORT: '导出',
  IMPORT: '导入',

  // 认证 + 安全
  LOGIN: '登录',
  LOGOUT: '登出',
  LOGIN_FAILED: '登录失败',
  PASSWORD_CHANGE: '密码修改',
  RESET_PASSWORD: '重置密码',
  PERMISSION_DENIED: '权限拒绝',
  SQL_INJECTION_ATTEMPT: 'SQL 注入拦截',
  unlock: '解锁',

  // 系统 + 配置
  STARTUP: '系统启动',
  SHUTDOWN: '系统关闭',
  CONFIG_CHANGE: '配置变更',
  CONFIG_ERROR: '配置错误',
  TEST: '测试操作',

  // 审计系统 (业务视图隐藏, 仅审计员可见)
  AUDIT_WRITE_FAILED: '审计写入失败',
  AUDIT_RETRY_SUCCESS: '审计重试成功',
  AUDIT_RETRY_FAILED: '审计重试失败',
  CASCADE_DELETE: '级联删除',

  // 性能监控 (业务视图隐藏)
  api_response_time: 'API 响应时间',
  db_query_time: '数据库查询时间',
  time: '性能计时',
  METRIC: '性能指标',
  UNKNOWN: '未识别操作'
}

/**
 * 内部技术 action 集合 (业务视图应该隐藏, 仅在审计视图显示)
 * 包含: 性能监控 + 审计系统元数据 + 未知
 */
export const INTERNAL_ACTIONS = new Set([
  'AUDIT_WRITE_FAILED',
  'AUDIT_RETRY_SUCCESS',
  'AUDIT_RETRY_FAILED',
  'api_response_time',
  'db_query_time',
  'time',
  'METRIC',
  'UNKNOWN'
])

/**
 * 是否是内部技术 action (业务视图应该隐藏)
 */
export function isInternalAction(action) {
  return INTERNAL_ACTIONS.has(action)
}

/**
 * 获取 object_type 业务名
 * @param {string} objectType - 后端 object_type 值
 * @returns {string} 业务名 (找不到回退原值)
 */
export function getObjectTypeLabel(objectType) {
  if (!objectType) return ''
  return OBJECT_TYPE_LABELS[objectType] || objectType
}

/**
 * 获取 action 业务名
 * @param {string} action - 后端 action 值
 * @returns {string} 业务动作 (找不到回退原值)
 */
export function getActionLabel(action) {
  if (!action) return '未知'
  return ACTION_LABELS[action] || action
}

/**
 * user_name 业务化
 * @param {string} userName
 * @returns {string}
 */
export function getUserNameDisplay(userName) {
  if (!userName) return '-'
  if (userName === 'system') return '系统'
  if (userName === '[REDACTED]') return '已脱敏'
  return userName
}

/**
 * _record 字段名业务化 (仅列表页字段过滤 + 详情页显示)
 * @param {string} fieldName
 * @returns {string}
 */
export const INTERNAL_FIELDS = new Set([
  '_record',          // 整个对象的 cud summary, 在 group header 已表明
  'extra_data',       // 元数据
  'cascade_root_id',  // 级联来源 ID
  'cascade_root_action'
])

/**
 * 是否是内部技术字段 (业务视图应该隐藏)
 */
export function isInternalField(fieldName) {
  return INTERNAL_FIELDS.has(fieldName)
}
