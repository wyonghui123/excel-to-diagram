# 组件迁移指南

本文档提供从旧组件迁移到新通用组件的详细指南，帮助开发者快速完成组件升级。

---

## 目录

1. [DataTable 到 MetaTable 迁移指南](#1-datatable-到-metatable-迁移指南)
2. [EditForm 到 MetaForm 迁移指南](#2-editform-到-metaform-迁移指南)
3. [内联 Dialog 到 AppModal 迁移指南](#3-内联-dialog-到-appmodal-迁移指南)
4. [新增功能使用指南](#4-新增功能使用指南)

---

## 1. DataTable 到 MetaTable 迁移指南

### 1.1 属性对照表

| DataTable 属性 | MetaTable 属性 | 变化说明 |
|---------------|---------------|---------|
| `data` | `data` | 无变化 |
| `columns` | `columns` | 结构优化，支持更多配置 |
| `loading` | `loading` | 无变化 |
| `pagination` | `pagination` | 结构扩展，支持更多配置 |
| `selectable` | `selectable` | 无变化 |
| - | `idKey` | 新增，默认 `'id'` |
| - | `rowKey` | 新增，默认 `'id'` |
| - | `selectedKeys` | 新增，用于受控多选 |
| - | `actions` | 新增，支持头部和行操作按钮 |
| - | `searchPlaceholder` | 新增，搜索框占位文本 |
| - | `searchFields` | 新增，指定搜索字段 |
| - | `showHeader` | 新增，控制头部显示 |
| - | `showPagination` | 新增，控制分页显示 |
| - | `stripe` | 新增，斑马纹样式 |
| - | `emptyType` | 新增，空状态类型 |
| - | `emptyTitle` | 新增，空状态标题 |
| - | `emptyDescription` | 新增，空状态描述 |
| - | `ariaLabel` | 新增，无障碍标签 |

### 1.2 列配置对照表

| DataTable 列属性 | MetaTable 列属性 | 变化说明 |
|-----------------|-----------------|---------|
| `key` | `key` | 无变化 |
| `title` | `label` | 属性名变更 |
| `visible` | `visible` | 无变化 |
| `sortable` | `sortable` | 无变化 |
| - | `width` | 新增，列宽度 |
| - | `type` | 新增，支持 `status`/`tag`/`time`/`ellipsis` |
| - | `statusMap` | 新增，状态映射配置 |
| - | `tagMap` | 新增，标签映射配置 |
| - | `slot` | 新增，启用插槽渲染 |
| - | `searchable` | 新增，控制是否可搜索 |

### 1.3 事件对照表

| DataTable 事件 | MetaTable 事件 | 变化说明 |
|---------------|---------------|---------|
| `row-click` | - | 移除，使用 `action` 事件替代 |
| `edit` | `action` | 合并到统一 action 事件 |
| `delete` | `action` | 合并到统一 action 事件 |
| `page-change` | `page-change` | 无变化 |
| `page-size-change` | `page-size-change` | 无变化 |
| `sort-change` | - | 内置排序，无需事件 |
| `selection-change` | `selection-change` | 无变化 |

### 1.4 分页配置对照

**DataTable 分页配置：**
```javascript
pagination: {
  page: 1,
  total: 100,
  pageSize: 10
}
```

**MetaTable 分页配置：**
```javascript
pagination: {
  current: 1,        // page -> current
  total: 100,
  pageSize: 10,
  showSizeChanger: true,   // 新增
  showQuickJumper: false,  // 新增
  pageSizeOptions: [10, 20, 50, 100]  // 新增
}
```

### 1.5 代码示例

#### 迁移前（DataTable）

```vue
<template>
  <DataTable
    :data="tableData"
    :columns="columns"
    :loading="loading"
    :pagination="pagination"
    :selectable="true"
    @edit="handleEdit"
    @delete="handleDelete"
    @page-change="handlePageChange"
    @selection-change="handleSelectionChange"
  />
</template>

<script setup>
const columns = [
  { key: 'name', title: '名称', sortable: true },
  { key: 'code', title: '编码' },
  { key: 'status', title: '状态' }
]

const pagination = {
  page: 1,
  total: 100,
  pageSize: 10
}

function handleEdit(row) {
  // 编辑逻辑
}

function handleDelete(row) {
  // 删除逻辑
}
</script>
```

#### 迁移后（MetaTable）

```vue
<template>
  <MetaTable
    :data="tableData"
    :columns="columns"
    :loading="loading"
    :pagination="pagination"
    :selectable="true"
    :selected-keys="selectedKeys"
    :actions="actions"
    @action="handleAction"
    @page-change="handlePageChange"
    @selection-change="handleSelectionChange"
  />
</template>

<script setup>
const columns = [
  { key: 'name', label: '名称', sortable: true },
  { key: 'code', label: '编码' },
  { 
    key: 'status', 
    label: '状态',
    type: 'status',
    statusMap: {
      active: { label: '启用', style: 'active' },
      inactive: { label: '停用', style: 'inactive' }
    }
  }
]

const pagination = {
  current: 1,
  total: 100,
  pageSize: 10,
  showSizeChanger: true
}

const actions = [
  { key: 'add', label: '新增', position: 'header', variant: 'primary' },
  { key: 'edit', label: '编辑', position: 'row' },
  { key: 'delete', label: '删除', position: 'row', variant: 'danger' }
]

function handleAction({ key, type, row }) {
  if (type === 'row') {
    if (key === 'edit') {
      // 编辑逻辑
    } else if (key === 'delete') {
      // 删除逻辑
    }
  }
}
</script>
```

---

## 2. EditForm 到 MetaForm 迁移指南

### 2.1 属性对照表

| EditForm 属性 | MetaForm 属性 | 变化说明 |
|--------------|--------------|---------|
| `data` | `modelValue` | 属性名变更，支持 v-model |
| `mode` | - | 移除，由业务层控制 |
| - | `fields` | 新增，字段配置数组 |
| - | `layout` | 新增，布局方式 |
| - | `labelPosition` | 新增，标签位置 |
| - | `labelWidth` | 新增，标签宽度 |
| - | `fieldVisibility` | 新增，字段条件显示 |
| - | `fieldDependencies` | 新增，字段联动配置 |

### 2.2 字段配置迁移

**EditForm 字段配置（硬编码）：**
```javascript
// EditForm 内部硬编码字段配置
const formFields = computed(() => {
  const typeFieldMap = {
    product: [
      { key: 'name', label: '产品名称', type: 'text', required: true },
      { key: 'code', label: '产品编码', type: 'text', required: true }
    ],
    // ...
  }
  return typeFieldMap[formData.value.object_type]
})
```

**MetaForm 字段配置（外部传入）：**
```javascript
const fields = [
  { 
    key: 'name', 
    label: '名称', 
    type: 'text', 
    required: true,
    placeholder: '请输入名称'
  },
  { 
    key: 'code', 
    label: '编码', 
    type: 'text',
    placeholder: '请输入编码'
  },
  { 
    key: 'type', 
    label: '类型', 
    type: 'select',
    options: [
      { label: '类型A', value: 'a' },
      { label: '类型B', value: 'b' }
    ]
  },
  { 
    key: 'description', 
    label: '描述', 
    type: 'textarea',
    rows: 4
  },
  {
    key: 'enabled',
    label: '启用状态',
    type: 'switch'
  }
]
```

### 2.3 验证迁移

**EditForm 验证（内部方法）：**
```javascript
function validate() {
  const requiredFields = formFields.value.filter(f => f.required)
  for (const field of requiredFields) {
    if (!formData.value[field.key]?.toString().trim()) {
      return false
    }
  }
  return true
}
```

**MetaForm 验证（支持自定义规则）：**
```javascript
const fields = [
  { 
    key: 'name', 
    label: '名称', 
    type: 'text', 
    required: true,
    requiredMessage: '请输入名称'
  },
  { 
    key: 'email', 
    label: '邮箱', 
    type: 'text',
    rules: [
      (value) => {
        if (!value) return true
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
        return emailRegex.test(value) || '请输入有效的邮箱地址'
      }
    ]
  },
  { 
    key: 'age', 
    label: '年龄', 
    type: 'number',
    rules: [
      (value) => {
        if (!value) return true
        return (value >= 1 && value <= 150) || '年龄必须在1-150之间'
      }
    ]
  }
]

// 使用
const formRef = ref(null)

async function handleSubmit() {
  const isValid = formRef.value.validateAll()
  if (isValid) {
    const formData = formRef.value.getFormData()
    // 提交逻辑
  }
}
```

### 2.4 代码示例

#### 迁移前（EditForm）

```vue
<template>
  <EditForm
    :data="editData"
    :mode="editMode"
    @save="handleSave"
    @cancel="handleCancel"
  />
</template>

<script setup>
const editData = ref({})
const editMode = ref('create')

function handleSave(data, continueEdit) {
  // 保存逻辑
}

function handleCancel() {
  // 取消逻辑
}
</script>
```

#### 迁移后（MetaForm）

```vue
<template>
  <AppModal
    v-model="showModal"
    :title="editMode === 'create' ? '新建' : '编辑'"
    :show-default-footer="true"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  >
    <MetaForm
      ref="formRef"
      v-model="formData"
      :fields="fields"
      layout="vertical"
      label-position="top"
      :field-visibility="fieldVisibility"
      :field-dependencies="fieldDependencies"
    />
  </AppModal>
</template>

<script setup>
const formRef = ref(null)
const showModal = ref(false)
const editMode = ref('create')
const formData = ref({})

const fields = [
  { key: 'name', label: '名称', type: 'text', required: true },
  { key: 'code', label: '编码', type: 'text', required: true },
  { key: 'type', label: '类型', type: 'select', options: typeOptions },
  { key: 'description', label: '描述', type: 'textarea' }
]

async function handleConfirm() {
  const isValid = formRef.value.validateAll()
  if (!isValid) return
  
  const data = formRef.value.getFormData()
  // 保存逻辑
}

function handleCancel() {
  showModal.value = false
}
</script>
```

---

## 3. 内联 Dialog 到 AppModal 迁移指南

### 3.1 模板结构对比

#### 迁移前（内联 Dialog）

```vue
<template>
  <div v-if="showDialog" class="dialog-overlay" @click="closeDialog">
    <div class="dialog-container" @click.stop>
      <div class="dialog-header">
        <h3>{{ dialogTitle }}</h3>
        <button class="close-btn" @click="closeDialog">×</button>
      </div>
      <div class="dialog-body">
        <slot></slot>
      </div>
      <div class="dialog-footer">
        <button @click="handleCancel">取消</button>
        <button @click="handleConfirm">确定</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
/* ... 更多样式 */
</style>
```

#### 迁移后（AppModal）

```vue
<template>
  <AppModal
    v-model="showDialog"
    :title="dialogTitle"
    :width="520"
    :show-default-footer="true"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  >
    <slot></slot>
  </AppModal>
</template>
```

### 3.2 属性对照表

| 内联 Dialog 属性 | AppModal 属性 | 变化说明 |
|-----------------|--------------|---------|
| `showDialog` | `v-model` | 使用 v-model 双向绑定 |
| `dialogTitle` | `title` | 属性名变更 |
| - | `width` | 新增，支持数字或字符串 |
| - | `showClose` | 新增，控制关闭按钮 |
| - | `showDefaultFooter` | 新增，显示默认底部按钮 |
| - | `confirmText` | 新增，确认按钮文本 |
| - | `cancelText` | 新增，取消按钮文本 |
| - | `confirmLoading` | 新增，确认按钮加载状态 |
| - | `closeOnClickOverlay` | 新增，点击遮罩关闭 |
| - | `closeOnPressEscape` | 新增，按 ESC 关闭 |
| - | `lockScroll` | 新增，锁定背景滚动 |
| - | `customClass` | 新增，自定义类名 |

### 3.3 事件处理迁移

#### 迁移前

```javascript
function closeDialog() {
  showDialog.value = false
}

function handleConfirm() {
  // 确认逻辑
  closeDialog()
}

function handleCancel() {
  closeDialog()
}

// 需要手动处理 ESC 键
onMounted(() => {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && showDialog.value) {
      closeDialog()
    }
  })
})
```

#### 迁移后

```javascript
// AppModal 内置 ESC 键处理和焦点管理
function handleConfirm() {
  // 确认逻辑
  // 无需手动关闭，由组件自动处理
}

function handleCancel() {
  // 取消逻辑
  // 无需手动关闭，由组件自动处理
}
```

### 3.4 插槽使用

```vue
<template>
  <AppModal v-model="showModal" title="编辑信息">
    <!-- 默认插槽：内容区域 -->
    <MetaForm ref="formRef" v-model="formData" :fields="fields" />
    
    <!-- 自定义头部 -->
    <template #header>
      <div class="custom-header">
        <h3>自定义标题</h3>
        <span class="subtitle">副标题</span>
      </div>
    </template>
    
    <!-- 自定义底部 -->
    <template #footer>
      <AppButton variant="secondary" @click="handleCancel">取消</AppButton>
      <AppButton variant="primary" :loading="saving" @click="handleSave">
        保存
      </AppButton>
    </template>
  </AppModal>
</template>
```

---

## 4. 新增功能使用指南

### 4.1 MetaTable 多选功能

MetaTable 提供了完善的多选功能，支持受控和非受控两种模式。

#### 基础用法

```vue
<template>
  <MetaTable
    :data="tableData"
    :columns="columns"
    :selectable="true"
    :selected-keys="selectedKeys"
    @selection-change="handleSelectionChange"
  />
</template>

<script setup>
const selectedKeys = ref([])

function handleSelectionChange(selectedRows) {
  console.log('选中的行:', selectedRows)
  // selectedKeys 会自动更新
}
</script>
```

#### 批量操作示例

```vue
<template>
  <div class="batch-operation">
    <MetaTable
      :data="tableData"
      :columns="columns"
      :selectable="true"
      :selected-keys="selectedKeys"
      :actions="tableActions"
      @selection-change="handleSelectionChange"
      @action="handleAction"
    />
    
    <div v-if="selectedKeys.length > 0" class="batch-bar">
      <span>已选择 {{ selectedKeys.length }} 项</span>
      <button @click="handleBatchDelete">批量删除</button>
      <button @click="handleBatchExport">批量导出</button>
    </div>
  </div>
</template>

<script setup>
const selectedKeys = ref([])

const tableActions = [
  { key: 'add', label: '新增', position: 'header', variant: 'primary' }
]

function handleSelectionChange(selectedRows) {
  selectedKeys.value = selectedRows.map(row => row.id)
}

function handleBatchDelete() {
  if (confirm(`确定删除选中的 ${selectedKeys.value.length} 项吗？`)) {
    // 批量删除逻辑
  }
}
</script>
```

### 4.2 MetaTable 分页功能

MetaTable 提供了功能完善的分页组件，支持页码切换、每页条数选择、快速跳转等功能。

#### 基础分页

```vue
<template>
  <MetaTable
    :data="tableData"
    :columns="columns"
    :pagination="pagination"
    @page-change="handlePageChange"
    @page-size-change="handlePageSizeChange"
  />
</template>

<script setup>
const tableData = ref([])
const pagination = ref({
  current: 1,
  total: 0,
  pageSize: 10
})

async function loadData() {
  const res = await api.getList({
    page: pagination.value.current,
    pageSize: pagination.value.pageSize
  })
  tableData.value = res.data
  pagination.value.total = res.total
}

function handlePageChange(page) {
  pagination.value.current = page
  loadData()
}

function handlePageSizeChange(size) {
  pagination.value.pageSize = size
  pagination.value.current = 1
  loadData()
}
</script>
```

#### 完整分页配置

```vue
<template>
  <MetaTable
    :data="tableData"
    :columns="columns"
    :pagination="{
      current: pagination.current,
      total: pagination.total,
      pageSize: pagination.pageSize,
      showSizeChanger: true,
      showQuickJumper: true,
      pageSizeOptions: [10, 20, 50, 100]
    }"
    @page-change="handlePageChange"
    @page-size-change="handlePageSizeChange"
  />
</template>
```

### 4.3 MetaForm 条件显示

MetaForm 支持基于表单数据的字段条件显示功能。

#### 基础用法

```vue
<template>
  <MetaForm
    v-model="formData"
    :fields="fields"
    :field-visibility="fieldVisibility"
  />
</template>

<script setup>
const formData = ref({
  type: '',
  otherType: ''
})

const fields = [
  { key: 'type', label: '类型', type: 'select', options: typeOptions },
  { key: 'otherType', label:其他类型', type: 'text' }
]

const fieldVisibility = {
  otherType: (formData) => formData.type === 'other'
}
</script>
```

#### 复杂条件示例

```vue
<script setup>
const formData = ref({
  userType: '',
  company: '',
  idNumber: ''
})

const fields = [
  { key: 'userType', label: '用户类型', type: 'select', options: [
    { label: '个人', value: 'personal' },
    { label: '企业', value: 'enterprise' }
  ]},
  { key: 'company', label: '公司名称', type: 'text' },
  { key: 'idNumber', label: '身份证号', type: 'text' },
  { key: 'creditCode', label: '统一社会信用代码', type: 'text' }
]

const fieldVisibility = {
  company: (formData) => formData.userType === 'enterprise',
  creditCode: (formData) => formData.userType === 'enterprise',
  idNumber: (formData) => formData.userType === 'personal'
}
</script>
```

### 4.4 MetaForm 字段联动

MetaForm 支持字段之间的联动效果，当一个字段值变化时，可以自动更新其他字段。

#### 基础联动示例

```vue
<template>
  <MetaForm
    ref="formRef"
    v-model="formData"
    :fields="fields"
    :field-dependencies="fieldDependencies"
  />
</template>

<script setup>
const formData = ref({
  province: '',
  city: '',
  district: ''
})

const cityOptions = ref([])
const districtOptions = ref([])

const fields = computed(() => [
  { 
    key: 'province', 
    label: '省份', 
    type: 'select', 
    options: provinceOptions 
  },
  { 
    key: 'city', 
    label: '城市', 
    type: 'select', 
    options: cityOptions.value 
  },
  { 
    key: 'district', 
    label: '区县', 
    type: 'select', 
    options: districtOptions.value 
  }
])

const fieldDependencies = {
  province: {
    onChange: (value, formData, context) => {
      // 清空下级字段
      context.setFieldValues({
        city: '',
        district: ''
      })
      // 加载城市数据
      loadCities(value)
    }
  },
  city: {
    onChange: (value, formData, context) => {
      // 清空区县
      context.setFieldValue('district', '')
      // 加载区县数据
      loadDistricts(value)
    }
  }
}

async function loadCities(provinceId) {
  const res = await api.getCities(provinceId)
  cityOptions.value = res.data
}

async function loadDistricts(cityId) {
  const res = await api.getDistricts(cityId)
  districtOptions.value = res.data
}
</script>
```

#### 价格计算联动示例

```vue
<script setup>
const formData = ref({
  quantity: 0,
  unitPrice: 0,
  discount: 0,
  totalPrice: 0
})

const fields = [
  { key: 'quantity', label: '数量', type: 'number' },
  { key: 'unitPrice', label: '单价', type: 'number' },
  { key: 'discount', label: '折扣(%)', type: 'number' },
  { key: 'totalPrice', label: '总价', type: 'number', disabled: true }
]

const fieldDependencies = {
  quantity: {
    onChange: () => calculateTotal()
  },
  unitPrice: {
    onChange: () => calculateTotal()
  },
  discount: {
    onChange: () => calculateTotal()
  }
}

function calculateTotal() {
  const { quantity, unitPrice, discount } = formData.value
  const total = quantity * unitPrice * (1 - discount / 100)
  formData.value.totalPrice = Math.round(total * 100) / 100
}
</script>
```

### 4.5 新组件使用示例

#### 完整的 CRUD 页面示例

```vue
<template>
  <div class="crud-page">
    <MetaTable
      :data="tableData"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      :selectable="true"
      :selected-keys="selectedKeys"
      :actions="tableActions"
      :empty-title="'暂无数据'"
      :empty-description="'点击新增按钮添加数据'"
      @action="handleAction"
      @selection-change="handleSelectionChange"
      @page-change="handlePageChange"
      @page-size-change="handlePageSizeChange"
    >
      <template #cell-status="{ row }">
        <span :class="['status-tag', `status-${row.status}`]">
          {{ statusMap[row.status] }}
        </span>
      </template>
    </MetaTable>

    <AppModal
      v-model="showModal"
      :title="modalTitle"
      width="600px"
      :show-default-footer="true"
      :confirm-loading="saving"
      @confirm="handleConfirm"
      @cancel="handleCancel"
    >
      <MetaForm
        ref="formRef"
        v-model="formData"
        :fields="formFields"
        layout="vertical"
        label-position="top"
        :field-visibility="fieldVisibility"
        :field-dependencies="fieldDependencies"
      />
    </AppModal>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'

const loading = ref(false)
const saving = ref(false)
const showModal = ref(false)
const editMode = ref('create')
const selectedKeys = ref([])
const formRef = ref(null)

const tableData = ref([])
const formData = ref({})

const pagination = reactive({
  current: 1,
  total: 0,
  pageSize: 10,
  showSizeChanger: true,
  showQuickJumper: true
})

const columns = [
  { key: 'name', label: '名称', sortable: true },
  { key: 'code', label: '编码' },
  { key: 'status', label: '状态', type: 'status', slot: true },
  { key: 'createdAt', label: '创建时间', type: 'time' }
]

const tableActions = [
  { key: 'add', label: '新增', position: 'header', variant: 'primary' },
  { key: 'edit', label: '编辑', position: 'row' },
  { key: 'delete', label: '删除', position: 'row', variant: 'danger' }
]

const formFields = computed(() => [
  { key: 'name', label: '名称', type: 'text', required: true },
  { key: 'code', label: '编码', type: 'text', required: true },
  { 
    key: 'type', 
    label: '类型', 
    type: 'select', 
    options: typeOptions.value 
  },
  { key: 'otherType', label: '其他类型', type: 'text' },
  { key: 'description', label: '描述', type: 'textarea', rows: 4 },
  { key: 'enabled', label: '启用', type: 'switch' }
])

const fieldVisibility = {
  otherType: (data) => data.type === 'other'
}

const fieldDependencies = {
  type: {
    onChange: (value, formData, context) => {
      if (value !== 'other') {
        context.setFieldValue('otherType', '')
      }
    }
  }
}

const modalTitle = computed(() => 
  editMode.value === 'create' ? '新增' : '编辑'
)

async function loadData() {
  loading.value = true
  try {
    const res = await api.getList({
      page: pagination.current,
      pageSize: pagination.pageSize
    })
    tableData.value = res.data
    pagination.total = res.total
  } finally {
    loading.value = false
  }
}

function handleAction({ key, type, row }) {
  if (key === 'add') {
    editMode.value = 'create'
    formData.value = {}
    showModal.value = true
  } else if (key === 'edit') {
    editMode.value = 'edit'
    formData.value = { ...row }
    showModal.value = true
  } else if (key === 'delete') {
    handleDelete(row)
  }
}

async function handleConfirm() {
  const isValid = formRef.value.validateAll()
  if (!isValid) return

  saving.value = true
  try {
    const data = formRef.value.getFormData()
    if (editMode.value === 'create') {
      await api.create(data)
    } else {
      await api.update(data.id, data)
    }
    showModal.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

function handleCancel() {
  showModal.value = false
}

async function handleDelete(row) {
  if (!confirm('确定删除该记录吗？')) return
  await api.delete(row.id)
  loadData()
}

function handleSelectionChange(rows) {
  selectedKeys.value = rows.map(r => r.id)
}

function handlePageChange(page) {
  pagination.current = page
  loadData()
}

function handlePageSizeChange(size) {
  pagination.pageSize = size
  pagination.current = 1
  loadData()
}

loadData()
</script>
```

---

## 附录：常见问题

### Q1: MetaTable 的排序是前端排序还是后端排序？

MetaTable 默认使用前端排序，对所有数据进行排序后显示。如果需要后端排序，可以通过监听排序状态变化并重新请求数据实现。

### Q2: MetaForm 如何实现异步验证？

可以在 `rules` 中返回 Promise：

```javascript
const fields = [
  {
    key: 'username',
    label: '用户名',
    type: 'text',
    rules: [
      async (value) => {
        if (!value) return true
        const exists = await checkUsernameExists(value)
        return !exists || '用户名已存在'
      }
    ]
  }
]
```

### Q3: AppModal 如何阻止关闭？

在 `confirm` 事件中，如果验证失败，不要设置 `v-model` 为 `false`，弹窗会保持打开状态。

### Q4: 如何自定义 MetaTable 的单元格渲染？

使用插槽：

```vue
<MetaTable :data="tableData" :columns="columns">
  <template #cell-customField="{ row, value }">
    <span class="custom-cell">{{ value }}</span>
  </template>
</MetaTable>
```

并在列配置中启用插槽：

```javascript
const columns = [
  { key: 'customField', label: '自定义字段', slot: true }
]
```

---

*文档版本：1.0.0*
*最后更新：2026-05-07*
