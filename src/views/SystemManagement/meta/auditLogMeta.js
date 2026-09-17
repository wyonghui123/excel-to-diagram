/**
 * 审计日志元数据定义
 * 用于驱动审计日志管理页面的列表、过滤和详情展示
 * 
 * 元数据驱动：与后端 audit_log.yaml 的 ui_view_config 保持同步
 */

export const auditLogMeta = {
  // 对象标识
  object: 'audit_log',
  name: '审计日志',
  description: '系统审计日志，记录所有业务对象的变更历史',

  // 列表配置
  list: {
    // 默认排序
    defaultSort: {
      field: 'created_at',
      direction: 'desc'
    },
    // 分页配置
    pagination: {
      pageSize: 20,
      pageSizes: [20, 50, 100]
    }
  },

  // 表格列定义（元数据驱动：与后端 YAML ui_view_config.list.columns 同步）
  tableColumns: [
    {
      key: 'id',
      label: '日志ID',
      type: 'text',
      width: 80,
      fixed: 'left'
    },
    {
      key: 'created_at',
      label: '操作时间',
      type: 'datetime',
      width: 160,
      sortable: true
    },
    // [FIX 2026-09-06 死列清理] 移除 log_category / log_level / action_kind / outcome 四列:
    // 1) list API (audit_api.py GET /logs) 的 SELECT 不返回这些字段, 列恒为空
    // 2) action_kind/outcome 仅存在于 audit_service 物化表, audit_logs 表无此列
    // 3) 本页所有日志均为 business/INFO (log_business 硬编码), 常量列无信息量
    {
      key: 'action',
      label: '操作类型',
      type: 'tag',
      width: 100,
      sortable: true,
      options: [
        { label: '创建', value: 'CREATE', color: 'success' },
        { label: '更新', value: 'UPDATE', color: 'warning' },
        { label: '删除', value: 'DELETE', color: 'danger' },
        { label: '关联', value: 'ASSOCIATE', color: 'info' },
        { label: '取消关联', value: 'DISSOCIATE', color: 'info' }
      ]
    },
    {
      key: 'object_type',
      label: '对象类型',
      type: 'text',
      width: 120,
      sortable: true
    },
    {
      key: 'object_id',
      label: '对象ID',
      type: 'text',
      width: 80
    },
    {
      // [FIX 2026-09-06 业务标识修正] 后端从未返回 formatted_identity (前端死字段),
      // 真实字段是后端 _generate_business_key 生成的 business_key
      key: 'business_key',
      label: '业务标识',
      type: 'text',
      width: 200,
      showOverflowTooltip: true
    },
    {
      key: 'field_name',
      label: '字段名',
      type: 'text',
      width: 120
    },
    {
      key: 'old_value',
      label: '旧值',
      type: 'text',
      width: 150,
      showOverflowTooltip: true
    },
    {
      key: 'new_value',
      label: '新值',
      type: 'text',
      width: 150,
      showOverflowTooltip: true
    },
    {
      key: 'user_name',
      label: '操作人',
      type: 'text',
      width: 120,
      sortable: true
    },
    {
      key: 'ip_address',
      label: 'IP地址',
      type: 'text',
      width: 130
    }
  ],

  // 过滤器定义（元数据驱动：从列配置自动生成）
  // [FIX 2026-09-06 死过滤器清理] 移除 log_category / log_level / action_kind / outcome:
  // list API 虽支持 log_category/log_level 查询参数, 但本页数据恒为 business/INFO,
  // 过滤无意义; action_kind/outcome 在 audit_logs 表中不存在
  filters: [
    {
      key: 'action',
      label: '操作类型',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '创建', value: 'CREATE' },
        { label: '更新', value: 'UPDATE' },
        { label: '删除', value: 'DELETE' },
        { label: '关联', value: 'ASSOCIATE' },
        { label: '取消关联', value: 'DISSOCIATE' }
      ],
      defaultValue: ''
    },
    {
      // [FIX 2026-09-06 角色迁移] 新增 org/permission_set;
      // role/user_group 为迁移前历史日志的 object_type, 保留以便检索历史记录
      key: 'object_type',
      label: '对象类型',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '用户', value: 'user' },
        { label: '组织', value: 'org' },
        { label: '权限集', value: 'permission_set' },
        { label: '组织（历史）', value: 'user_group' },
        { label: '权限集（历史）', value: 'role' },
        { label: '产品', value: 'product' },
        { label: '版本', value: 'version' },
        { label: '领域', value: 'domain' },
        { label: '子域', value: 'sub_domain' },
        { label: '服务模块', value: 'service_module' },
        { label: '业务对象', value: 'business_object' },
        { label: '关系', value: 'relationship' },
        { label: '标注', value: 'annotation' },
        { label: '枚举类型', value: 'enum_type' },
        { label: '枚举值', value: 'enum_value' }
      ],
      defaultValue: ''
    },
    {
      key: 'user_name',
      label: '操作人',
      type: 'select',
      options: [],
      placeholder: '请选择操作人',
      async: true,
      apiUrl: '/api/v2/bo/user?page_size=1000'
    },
    {
      key: 'date_range',
      label: '时间范围',
      type: 'datetime-range',
      placeholder: ['开始时间', '结束时间'],
      defaultValue: []
    }
  ],

  // 详情抽屉配置
  detail: {
    title: '审计日志详情',
    width: '640px',
    sections: [
      {
        title: '基本信息',
        fields: [
          { key: 'id', label: '记录ID', type: 'text' },
          { key: 'created_at', label: '操作时间', type: 'datetime' },
          // [FIX 2026-09-06 死字段清理] 移除 log_category/log_level:
          // detail API SELECT 不返回这两个字段, 且值恒为 business/INFO
          { key: 'action', label: '操作类型', type: 'tag' },
          { key: 'object_type', label: '对象类型', type: 'text' },
          { key: 'object_id', label: '对象ID', type: 'text' },
          // [FIX 2026-09-06] formatted_identity 为前端死字段, 后端真实字段是 business_key
          { key: 'business_key', label: '业务标识', type: 'text' }
        ]
      },
      {
        title: '变更详情',
        fields: [
          { key: 'field_name', label: '字段名', type: 'text' },
          { key: 'old_value', label: '旧值', type: 'textarea' },
          { key: 'new_value', label: '新值', type: 'textarea' }
        ]
      },
      {
        title: '操作人信息',
        fields: [
          { key: 'user_id', label: '用户ID', type: 'text' },
          { key: 'user_name', label: '用户名', type: 'text' },
          { key: 'ip_address', label: 'IP地址', type: 'text' },
          { key: 'user_agent', label: '用户代理', type: 'textarea' }
        ]
      },
      {
        title: '追踪信息',
        fields: [
          { key: 'trace_id', label: '链路追踪ID', type: 'text' },
          { key: 'transaction_id', label: '事务ID', type: 'text' },
          { key: 'status', label: '状态', type: 'tag' }
        ]
      }
    ]
  },

  // API配置
  api: {
    baseUrl: '/api/v1/audit',
    endpoints: {
      list: {
        method: 'GET',
        path: '/logs',
        params: {
          page: 'page',
          pageSize: 'page_size',
          logCategory: 'log_category',
          logLevel: 'log_level',
          action: 'action',
          objectType: 'object_type',
          userName: 'user_name',
          startDate: 'start_date',
          endDate: 'end_date',
          // [DECORATIVE] FR-LOG-012: v2 filters
          actionKind: 'action_kind',
          outcome: 'outcome',
          parentActionId: 'parent_action_id'
        }
      },
      detail: {
        method: 'GET',
        path: '/logs/:id'
      }
    }
  }
}
