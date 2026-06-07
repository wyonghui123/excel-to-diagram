# ExportDialog 组件

通用的数据导出对话框组件，支持字段选择、导出选项配置和文件下载。

## 功能特性

- ✅ 字段选择器（多选）
- ✅ 全选/取消全选
- ✅ 导出选项配置
- ✅ 导出筛选后的数据
- ✅ 排除敏感字段
- ✅ 导出进度显示
- ✅ 文件自动下载

## 使用方法

### 基本用法

```vue
<template>
  <div>
    <button @click="showExport = true">导出数据</button>
    
    <ExportDialog
      v-model:visible="showExport"
      object-type="user"
      :fields="exportFields"
      @success="handleExportSuccess"
      @close="showExport = false"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ExportDialog from '@/components/common/ExportDialog'

const showExport = ref(false)

const exportFields = [
  { key: 'username', label: '用户名' },
  { key: 'display_name', label: '显示名称' },
  { key: 'email', label: '邮箱' },
  { key: 'status', label: '状态' },
  { key: 'created_at', label: '创建时间' }
]

function handleExportSuccess() {
  console.log('导出成功')
}
</script>
```

### 带筛选条件导出

```vue
<template>
  <ExportDialog
    v-model:visible="showExport"
    object-type="user"
    :fields="exportFields"
    :filters="currentFilters"
    @success="handleExportSuccess"
    @close="showExport = false"
  />
</template>

<script setup>
const currentFilters = {
  status: 'active',
  department: 'IT'
}
</script>
```

### 带上下文参数

```vue
<ExportDialog
  v-model:visible="showExport"
  object-type="business_object"
  :fields="exportFields"
  :context="{ version_id: 1, product_id: 2 }"
  @success="handleExportSuccess"
  @close="showExport = false"
/>
```

## Props

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| visible | Boolean | 否 | false | 控制对话框显示/隐藏 |
| objectType | String | 是 | - | 对象类型（如 'user', 'role' 等） |
| fields | Array | 否 | [] | 可导出的字段列表 |
| context | Object | 否 | {} | 上下文参数（如 version_id, product_id 等） |
| filters | Object | 否 | {} | 当前筛选条件 |
| exportOptions | Object | 否 | { includeFilters: true, excludeSensitive: true } | 导出选项配置 |

### fields 格式

支持两种格式：

```javascript
// 格式1：字符串数组
const fields = ['username', 'email', 'status']

// 格式2：对象数组（推荐）
const fields = [
  { key: 'username', label: '用户名' },
  { key: 'email', label: '邮箱' },
  { key: 'status', label: '状态' }
]
```

## Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| close | - | 关闭对话框时触发 |
| success | - | 导出成功时触发 |

## 导出选项

组件支持以下导出选项：

- **导出筛选后的数据**: 是否应用当前的筛选条件
- **排除敏感字段**: 是否排除敏感字段（如 password, salt 等）

## API依赖

组件依赖以下API端点：

- `POST /api/v1/export` - 导出数据

## 示例

### 用户管理页面导出

```vue
<template>
  <div class="user-management">
    <button @click="showExport = true">导出用户</button>
    
    <ExportDialog
      v-model:visible="showExport"
      object-type="user"
      :fields="userFields"
      :filters="tableFilters"
      :export-options="{ includeFilters: true, excludeSensitive: true }"
      @success="showSuccessMessage"
      @close="showExport = false"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ExportDialog from '@/components/common/ExportDialog'

const showExport = ref(false)
const tableFilters = ref({})

const userFields = [
  { key: 'username', label: '用户名' },
  { key: 'display_name', label: '显示名称' },
  { key: 'email', label: '邮箱' },
  { key: 'status', label: '状态' },
  { key: 'created_at', label: '创建时间' }
]

function showSuccessMessage() {
  console.log('导出成功')
}
</script>
```

### 架构数据导出

```vue
<template>
  <div class="arch-data-management">
    <button @click="showExport = true">导出架构数据</button>
    
    <ExportDialog
      v-model:visible="showExport"
      object-type="business_object"
      :fields="boFields"
      :context="{ version_id: currentVersion.id, product_id: currentProduct.id }"
      @success="loadArchData"
      @close="showExport = false"
    />
  </div>
</template>
```

## 注意事项

1. 确保后端API已实现导出端点
2. 导出大量数据时可能需要较长时间，请耐心等待
3. 导出成功后会自动触发文件下载
4. 建议排除敏感字段，避免数据泄露
