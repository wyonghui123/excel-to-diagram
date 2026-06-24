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
 * 内部技术字段精确集合 (业务视图应该隐藏)
 *
 * 隐藏规则:
 * 1. 精确匹配: 以下 Set 中的字段名
 * 2. 模式匹配: isInternalField() 中补充 _id 后缀等规则
 */
export const INTERNAL_FIELDS = new Set([
  '_record',          // 整个对象的 cud summary, 在 group header 已表明
  'extra_data',       // 元数据
  'cascade_root_id',  // 级联来源 ID
  'cascade_root_action',
  // 系统时间戳/操作人 (业务人员无需在变更字段中看到)
  'id',
  'created_at',
  'updated_at',
  'created_by',
  'updated_by',
  // annotation 技术字段
  'target_type',
  'target_id',
  // [FIX 2026-06-19] AI Agent 元数据 (业务视图隐藏)
  'agent_id',
  'agent_session_id',
  'agent_reasoning',
  'tool_call_id',
  // [FIX 2026-06-19] 审计系统状态字段
  'error_message',
  'retry_count',
  'status',
  'status_entered_at',
  'row_hash',
  'prev_hash',
  'retention_until',
])

/**
 * FK 外键字段后缀模式: *_id (但不含 'id' 本身)
 * 匹配: version_id, source_bo_id, domain_id, product_id, owner_id 等
 * 不匹配: id (已在上面的 Set 中)
 */
const FK_ID_SUFFIX_RE = /^(?!id$).*_id$/

/**
 * Virtual display field suffix pattern: source_xxx_name / target_xxx_code
 * These are redundant fields derived from FK JOINs; FK structured values already include target_display
 */
const VIRTUAL_DISPLAY_RE = /^(source|target)_.+_(name|code)$/

/**
 * Business-visible FK fields - these have _id suffix but should NOT be hidden
 * because they carry business meaning (e.g. owner_id = who is responsible)
 */
const BUSINESS_VISIBLE_FK_FIELDS = new Set([
  'owner_id',  // product owner - business meaningful
])

/**
 * 是否是内部技术字段 (业务视图应该隐藏)
 *
 * 隐藏规则:
 * 1. 精确匹配 INTERNAL_FIELDS 集合
 * 2. FK 外键字段: *_id 后缀 (version_id, source_bo_id 等), 但排除 BUSINESS_VISIBLE_FK_FIELDS
 * 3. 虚拟冗余显示字段: source_xxx_name, target_xxx_code 等
 */
export function isInternalField(fieldName) {
  if (!fieldName) return false
  if (INTERNAL_FIELDS.has(fieldName)) return true
  if (BUSINESS_VISIBLE_FK_FIELDS.has(fieldName)) return false
  if (FK_ID_SUFFIX_RE.test(fieldName)) return true
  if (VIRTUAL_DISPLAY_RE.test(fieldName)) return true
  return false
}

/**
 * 字段名 → 业务名 翻译表
 *
 * 把技术字段名翻译为业务人员可理解的术语
 * 优先级: 此表 > 原字段名
 */
export const FIELD_LABELS = {
  // 通用业务字段
  code: '编码',
  name: '名称',
  description: '描述',
  is_current: '当前版本',
  is_active: '是否活跃',
  visibility: '可见性',

  // relationship (业务关系)
  relation_type: '关系类型',
  relation_direction: '关系方向',
  relation_desc: '关系描述',
  relation_code: '关系编码',
  source_code: '来源对象',
  target_code: '目标对象',

  // annotation (备注)
  category: '分类',
  content: '内容',

  // product
  owner_id: '负责人',

  // [FIX 2026-06-19 业务化] enum_type 字段
  mutability: '可变性',
  allow_custom_values: '允许自定义值',
  is_default: '是否默认',
  display_order: '显示顺序',
  sort_order: '排序',

  // [FIX 2026-06-19 业务化] 通用布尔/数值
  is_archived: '是否归档',
  is_hidden: '是否隐藏',
  is_required: '是否必填',
  max_length: '最大长度',
  min_length: '最小长度',
  default_value: '默认值',
}

/**
 * 枚举值 → 业务值 翻译表
 *
 * 把技术枚举值翻译为业务人员可理解的中文
 */
export const FIELD_VALUE_LABELS = {
  // 关系方向
  BIDIRECTIONAL: '双向',
  UNIDIRECTIONAL: '单向',

  // 关系类型
  UPDATES: '更新',
  DEPENDS_ON: '依赖',
  CALLS: '调用',
  IMPLEMENTS: '实现',
  EXTENDS: '扩展',
  REFERENCES: '引用',
  CONSUMES: '消费',
  PRODUCES: '生产',
  USES: '使用',
  COMPOSES: '组合',
  AGGREGATES: '聚合',

  // 可见性
  public: '公开',
  private: '私有',
  internal: '内部',
  draft: '草稿',

  // [FIX 2026-06-24 业务化] 关系方向 (PUSH/PULL 是技术传输方向, 业务翻译)
  PUSH: '推送',
  PULL: '拉取',

  // [FIX 2026-06-24 业务化] annotation 备注分类
  warning: '警告',
  info: '信息',
  error: '错误',
  success: '成功',
  danger: '危险',
  tip: '提示',

  // [FIX 2026-06-19 业务化] mutability (可变性)
  readonly: '只读',
  fully_editable: '允许',
  fullEditable: '允许',
  half_editable: '半可编辑',
  halfEditable: '半可编辑',
  immutable: '不可变',

  // 布尔值
  true: '是',
  false: '否',
  True: '是',
  False: '否',
}

/**
 * 获取字段业务名
 * @param {string} fieldName - 后端字段名
 * @returns {string} 业务名 (找不到回退格式化后的字段名)
 */
export function getFieldLabel(fieldName) {
  if (!fieldName) return ''
  if (FIELD_LABELS[fieldName]) return FIELD_LABELS[fieldName]
  // 回退: 把下划线分隔转为更可读的格式 (relation_type → Relation Type)
  // 但优先用翻译表
  return fieldName
}

/**
 * 获取字段值业务显示
 * @param {string} value - 后端字段值
 * @param {string} [fieldName] - 字段名 (用于上下文相关翻译)
 * @returns {string} 业务值
 */
export function getFieldValueDisplay(value, fieldName) {
  if (value === null || value === undefined || value === '') return '(空)'
  const str = String(value)

  // 1. FK 结构化值: {"target_type":"business_object","target_id":470,"target_key":"BO_PO","target_display":"采购订单"}
  //    → 显示 target_display
  if (str.startsWith('{')) {
    try {
      const parsed = JSON.parse(str)
      if (parsed.target_display) return parsed.target_display
      if (parsed.target_key) return parsed.target_key
      // 降级: 显示 JSON 中的可读部分
      return str
    } catch {
      // 不是 JSON, 继续后续处理
    }
  }

  // 2. 枚举值翻译
  if (FIELD_VALUE_LABELS[str]) return FIELD_VALUE_LABELS[str]

  // 3. 原值
  return str
}
