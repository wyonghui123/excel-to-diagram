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
    {
      key: 'log_category',
      label: '日志类型',
      type: 'tag',
      width: 100,
      sortable: true,
      options: [
        { label: '业务审计', value: 'business', color: 'primary' },
        { label: '安全日志', value: 'security', color: 'danger' },
        { label: '运营日志', value: 'operation', color: 'info' },
        { label: '性能日志', value: 'performance', color: 'warning' },
        { label: '系统日志', value: 'system', color: 'default' }
      ]
    },
    {
      key: 'log_level',
      label: '日志级别',
      type: 'tag',
      width: 80,
      sortable: true,
      options: [
        { label: '调试', value: 'DEBUG', color: 'default' },
        { label: '信息', value: 'INFO', color: 'info' },
        { label: '警告', value: 'WARNING', color: 'warning' },
        { label: '错误', value: 'ERROR', color: 'danger' },
        { label: '严重', value: 'CRITICAL', color: 'danger' }
      ]
    },
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
      // [DECORATIVE] FR-LOG-012: action_kind 列
      key: 'action_kind',
      label: 'Action Kind',
      type: 'tag',
      width: 110,
      sortable: true,
      options: [
        { label: '[DECORATIVE] Instance', value: 'instance', color: 'primary' },
        { label: '[SYMBOL] Static', value: 'static', color: 'info' }
      ]
    },
    {
      // [DECORATIVE] FR-LOG-012: outcome 列
      key: 'outcome',
      label: '执行结果',
      type: 'tag',
      width: 100,
      sortable: true,
      options: [
        { label: '[OK] Success', value: 'success', color: 'success' },
        { label: '[X] Failure', value: 'failure', color: 'danger' },
        { label: '[SYMBOL] Denied', value: 'denied', color: 'warning' },
        { label: '[REFRESH] Retry', value: 'retry', color: 'info' }
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
      key: 'formatted_identity',
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
  filters: [
    {
      key: 'log_category',
      label: '日志类型',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '业务审计', value: 'business' },
        { label: '安全日志', value: 'security' },
        { label: '运营日志', value: 'operation' },
        { label: '性能日志', value: 'performance' },
        { label: '系统日志', value: 'system' }
      ],
      defaultValue: ''
    },
    {
      key: 'log_level',
      label: '日志级别',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '调试', value: 'DEBUG' },
        { label: '信息', value: 'INFO' },
        { label: '警告', value: 'WARNING' },
        { label: '错误', value: 'ERROR' },
        { label: '严重', value: 'CRITICAL' }
      ],
      defaultValue: ''
    },
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
      key: 'object_type',
      label: '对象类型',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '用户', value: 'user' },
        { label: '角色', value: 'role' },
        { label: '用户组', value: 'user_group' },
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
      // [DECORATIVE] FR-LOG-012: action_kind filter
      key: 'action_kind',
      label: 'Action Kind',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '[DECORATIVE] Instance', value: 'instance' },
        { label: '[SYMBOL] Static', value: 'static' }
      ],
      defaultValue: ''
    },
    {
      // [DECORATIVE] FR-LOG-012: outcome filter
      key: 'outcome',
      label: '执行结果',
      type: 'select',
      options: [
        { label: '全部', value: '' },
        { label: '[OK] Success', value: 'success' },
        { label: '[X] Failure', value: 'failure' },
        { label: '[SYMBOL] Denied', value: 'denied' },
        { label: '[REFRESH] Retry', value: 'retry' }
      ],
      defaultValue: ''
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
          { key: 'log_category', label: '日志类型', type: 'tag', options: [
            { label: '业务审计', value: 'business', color: 'primary' },
            { label: '安全日志', value: 'security', color: 'danger' },
            { label: '运营日志', value: 'operation', color: 'info' },
            { label: '性能日志', value: 'performance', color: 'warning' },
            { label: '系统日志', value: 'system', color: 'default' }
          ]},
          { key: 'log_level', label: '日志级别', type: 'tag', options: [
            { label: '调试', value: 'DEBUG', color: 'default' },
            { label: '信息', value: 'INFO', color: 'info' },
            { label: '警告', value: 'WARNING', color: 'warning' },
            { label: '错误', value: 'ERROR', color: 'danger' },
            { label: '严重', value: 'CRITICAL', color: 'danger' }
          ]},
          { key: 'action', label: '操作类型', type: 'tag' },
          { key: 'object_type', label: '对象类型', type: 'text' },
          { key: 'object_id', label: '对象ID', type: 'text' },
          { key: 'formatted_identity', label: '业务标识', type: 'text' }
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
