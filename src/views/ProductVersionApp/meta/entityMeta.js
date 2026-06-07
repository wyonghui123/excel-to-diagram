export const productMeta = {
  entity: 'product',
  label: '产品',
  apiBase: '/api/v2/bo/product',
  fields: [
    {
      key: 'name',
      label: '名称',
      type: 'text',
      required: true,
      placeholder: '请输入产品名称',
      requiredMessage: '请输入产品名称'
    },
    {
      key: 'code',
      label: '编码',
      type: 'text',
      required: true,
      placeholder: '请输入产品编码',
      requiredMessage: '请输入产品编码'
    },
    {
      key: 'description',
      label: '描述',
      type: 'textarea',
      rows: 3,
      placeholder: '请输入产品描述'
    },
    {
      key: 'status',
      label: '状态',
      type: 'select',
      defaultValue: 'active',
      options: [
        { label: '启用', value: 'active' },
        { label: '停用', value: 'inactive' }
      ]
    }
  ],
  tableColumns: [
    {
      key: 'name',
      label: '产品名称',
      width: '160px',
      type: 'text'
    },
    {
      key: 'code',
      label: '产品编码',
      width: '140px',
      type: 'text'
    },
    {
      key: 'status',
      label: '状态',
      width: '100px',
      type: 'status',
      statusMap: {
        active: { style: 'active', label: '启用' },
        inactive: { style: 'inactive', label: '停用' },
        development: { style: 'warning', label: '开发中' }
      }
    },
    {
      key: 'is_current',
      label: '当前版本',
      width: '90px',
      type: 'tag'
    },
    {
      key: 'description',
      label: '描述',
      type: 'ellipsis'
    },
    {
      key: 'created_at',
      label: '创建时间',
      width: '160px',
      type: 'time'
    }
  ]
}

export const versionMeta = {
  entity: 'version',
  label: '版本',
  apiBase: '/api/v2/bo/version',
  fields: [
    {
      key: 'name',
      label: '版本名称',
      type: 'text',
      required: true,
      placeholder: '请输入版本名称',
      requiredMessage: '请输入版本名称'
    },
    {
      key: 'code',
      label: '版本号',
      type: 'text',
      required: true,
      placeholder: '请输入版本号，如 V1.0',
      requiredMessage: '版本号不能为空'
    },
    {
      key: 'description',
      label: '描述',
      type: 'textarea',
      rows: 3,
      placeholder: '请输入版本描述'
    },
    {
      key: 'status',
      label: '状态',
      type: 'select',
      defaultValue: 'active',
      options: [
        { label: '开发中', value: 'development' },
        { label: '启用', value: 'active' },
        { label: '停用', value: 'inactive' }
      ]
    },
    {
      key: 'is_current',
      label: '当前版本',
      type: 'checkbox',
      checkboxLabel: '设为当前版本',
      defaultValue: false
    }
  ],
  tableColumns: [
    {
      key: 'name',
      label: '版本名称',
      width: '140px',
      sortable: true
    },
    {
      key: 'code',
      label: '版本号',
      width: '120px',
      sortable: true
    },
    {
      key: 'status',
      label: '状态',
      width: '100px',
      type: 'status',
      statusMap: {
        active: { style: 'active', label: '启用' },
        inactive: { style: 'inactive', label: '停用' },
        development: { style: 'warning', label: '开发中' }
      }
    },
    {
      key: 'is_current',
      label: '当前版本',
      width: '90px',
      type: 'tag',
      tagMap: {
        1: { style: 'primary', label: '当前' },
        0: { style: 'default', label: '-' },
        true: { style: 'primary', label: '当前' },
        false: { style: 'default', label: '-' }
      }
    },
    {
      key: 'description',
      label: '描述',
      type: 'ellipsis'
    },
    {
      key: 'created_at',
      label: '创建时间',
      width: '160px',
      type: 'time'
    }
  ],
  actions: [
    { key: 'edit', label: '编辑', variant: 'default', position: 'row' },
    { key: 'delete', label: '删除', variant: 'danger', position: 'row' },
    { key: 'open-arch-data', label: '进入数据管理', variant: 'success', position: 'row' },
    { key: 'view-history', label: '日志', variant: 'default', position: 'row' }
  ],
  headerActions: [
    { key: 'create', label: '新增版本', variant: 'primary', icon: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 3v10M3 8h10"/></svg>' }
  ]
}
