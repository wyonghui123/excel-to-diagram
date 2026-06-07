# 单一事实元数据模型驱动的批量操作实现方案

## 当前问题

❌ **不是真正的元数据驱动**
- MetaTable 组件不支持 batch_actions
- 需要手动在每个页面引入 ImportDialog 和 ExportDialog
- 需要手动绑定事件处理

## 解决方案

### 方案：增强 MetaTable 组件，自动支持批量操作

#### 1. MetaTable.vue 增强

```vue
<template>
  <div class="meta-table">
    <!-- 批量操作工具栏 -->
    <div v-if="selectedRows.length > 0 && batchActions.length > 0" class="batch-actions-toolbar">
      <span class="selected-count">已选择 {{ selectedRows.length }} 项</span>
      <div class="batch-actions">
        <button
          v-for="action in batchActions"
          :key="action.key"
          class="batch-action-btn"
          :class="`batch-action-btn--${action.variant || 'default'}`"
          @click="handleBatchAction(action)"
        >
          {{ action.label }}
        </button>
      </div>
    </div>

    <!-- 表格内容 -->
    <table class="mt-table">
      <!-- ... -->
    </table>

    <!-- 导入对话框（自动集成） -->
    <ImportDialog
      v-model:visible="showImportDialog"
      :object-type="objectType"
      :context="context"
      @success="handleImportSuccess"
      @close="showImportDialog = false"
    />

    <!-- 导出对话框（自动集成） -->
    <ExportDialog
      v-model:visible="showExportDialog"
      :object-type="objectType"
      :fields="exportFields"
      :filters="currentFilters"
      :context="context"
      @success="handleExportSuccess"
      @close="showExportDialog = false"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import ImportDialog from '@/components/common/ImportDialog'
import ExportDialog from '@/components/common/ExportDialog'

const props = defineProps({
  // ... 其他 props
  batchActions: {
    type: Array,
    default: () => []
  },
  exportFields: {
    type: Array,
    default: () => []
  },
  context: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['batch-action', 'refresh'])

const selectedRows = ref([])
const showImportDialog = ref(false)
const showExportDialog = ref(false)

function handleBatchAction(action) {
  if (action.key === 'delete') {
    handleBatchDelete(action)
  } else if (action.key === 'export') {
    showExportDialog.value = true
  } else if (action.key === 'import') {
    showImportDialog.value = true
  } else {
    emit('batch-action', { action, rows: selectedRows.value })
  }
}

async function handleBatchDelete(action) {
  const message = action.confirmMessage.replace('{count}', selectedRows.value.length)
  
  if (confirm(message)) {
    emit('batch-action', { 
      action: { ...action, key: 'batch_delete' }, 
      rows: selectedRows.value 
    })
  }
}

function handleImportSuccess() {
  emit('refresh')
}

function handleExportSuccess() {
  // 导出成功
}
</script>
```

#### 2. useMetaList.js 自动集成

```javascript
// 自动从元数据加载批量操作配置
async function _loadMetaConfig() {
  // ... 现有逻辑
  
  // 加载批量操作配置
  if (listConfig.batch_actions) {
    batchActions.value = _transformActions(listConfig.batch_actions)
  }
  
  // 加载导出字段配置
  if (listConfig.exportOptions?.includeFields) {
    exportFields.value = listConfig.exportOptions.includeFields.map(field => ({
      key: field,
      label: _getFieldLabel(field)
    }))
  }
}
```

#### 3. UserManagement.vue 简化

```vue
<template>
  <MetaTable
    :data="data"
    :columns="columns"
    :batch-actions="batchActions"
    :export-fields="exportFields"
    :context="{}"
    @batch-action="handleBatchAction"
    @refresh="loadList"
  />
</template>

<script setup>
import { useMetaList } from '@/composables/useMetaList'

const {
  data,
  columns,
  batchActions,
  exportFields,
  loadList,
  handleBatchAction
} = useMetaList('user')
</script>
```

## 优势

✅ **真正的元数据驱动**
- 只需配置元数据，无需手动引入组件
- MetaTable 自动根据 batch_actions 生成UI

✅ **单一事实来源**
- 所有配置在 userMeta.js 中
- 前端组件自动读取配置

✅ **零代码重复**
- 不需要在每个页面重复引入 ImportDialog 和 ExportDialog
- 批量操作逻辑统一在 MetaTable 中

## 实施步骤

1. 增强 MetaTable 组件，支持 batch_actions
2. 自动集成 ImportDialog 和 ExportDialog
3. 简化页面组件，只使用 MetaTable
4. 测试验证

## 验收标准

- [ ] MetaTable 自动显示批量操作按钮
- [ ] 点击按钮自动打开对应的对话框
- [ ] 页面代码零手动引入
- [ ] 所有配置来自元数据
