<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="800px"
    :destroy-on-close="true"
    class="assignment-dialog"
    @open="handleOpen"
    @close="handleClose"
  >
    <div class="ad-content">
      <!-- 搜索栏 -->
      <div v-if="targetType" class="vh-search-bar">
        <el-input
          ref="searchInputRef"
          v-model="dialogSearchQuery"
          placeholder="输入关键词实时搜索..."
          :prefix-icon="Search"
          clearable
          @input="handleSearchInput"
          @clear="handleSearchClear"
        />
      </div>

      <MetaListPage
        ref="metaListRef"
        v-if="targetType"
        :object-type="targetType"
        :display-mode="'dialog'"
        :hide-toolbar="true"
        :columns-override="displayColumnsForMeta"
        :exclude-ids="excludeIds"
        :options="{ autoLoad: true, pageSize: 15, pageSizes: [15, 30, 50, 100] }"
        :enable-detail="false"
        :enable-auto-crud="false"
        @selection-change="handleSelectionChange"
      />
      <div v-else class="ad-loading">
        <span>加载配置中...</span>
      </div>
    </div>

    <template #footer>
      <div class="ad-footer">
        <span v-if="selectedItems.length > 0" class="ad-selected-count">
          已选择 {{ selectedItems.length }} 项
        </span>
        <div class="ad-footer__actions">
          <el-button @click="handleClose">取消</el-button>
          <el-button
            type="primary"
            :disabled="selectedItems.length === 0"
            :loading="submitting"
            @click="handleSubmit"
          >
            确定
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'
import boService from '@/services/boService'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  objectType: {
    type: String,
    required: true
  },
  objectId: {
    type: [String, Number],
    required: true
  },
  associationName: {
    type: String,
    required: true
  },
  config: {
    type: Object,
    default: () => ({})
  },
  excludeIds: {
    type: Array,
    default: () => []
  },
  multiple: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'success'])

const message = useCrudMessage()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const submitting = ref(false)
const selectedItems = ref([])
const metaListRef = ref(null)
const searchInputRef = ref(null)
const dialogSearchQuery = ref('')
let searchTimer = null

const dialogTitle = computed(() => {
  return props.config?.display?.label
    ? `添加${props.config.display.label}`
    : '添加关联'
})

const targetType = computed(() => {
  return props.config?.target_type
})

const displayColumnsForMeta = computed(() => {
  if (props.config?.display?.columns) {
    return props.config.display.columns.map(col => {
      if (typeof col === 'string') {
        return { field: col, label: col }
      }
      return {
        field: col.id || col.field,
        label: col.label,
        width: col.width
      }
    })
  }
  return null
})

function handleSelectionChange(selection) {
  selectedItems.value = selection
}

function handleOpen() {
  dialogSearchQuery.value = ''
  selectedItems.value = []
  // 延迟聚焦搜索框
  setTimeout(() => {
    if (searchInputRef.value?.focus) {
      searchInputRef.value.focus()
    }
  }, 350)
}

// 实时搜索
function handleSearchInput(query) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    const keyword = query || ''
    if (metaListRef.value) {
      // [FIX 2026-06-14] 使用 setKeyword 方法而非直接赋值 keyword.value
      // 因为 defineExpose 暴露的 ref 会被 Vue setupState proxy 自动 unwrap,
      // metaListRef.value.keyword 是字符串而非 ref 对象, 直接赋值无效
      if (typeof metaListRef.value.setKeyword === 'function') {
        metaListRef.value.setKeyword(keyword)
      }
      metaListRef.value.loadList()
    }
  }, 300)
}

function handleSearchClear() {
  dialogSearchQuery.value = ''
  if (searchTimer) clearTimeout(searchTimer)
  if (metaListRef.value) {
    if (typeof metaListRef.value.setKeyword === 'function') {
      metaListRef.value.setKeyword('')
    }
    metaListRef.value.loadList()
  }
}

async function handleSubmit() {
  if (selectedItems.value.length === 0) {
    message.warning('请选择要添加的记录')
    return
  }

  submitting.value = true

  try {
    const targetIds = selectedItems.value.map(item => item.id)
    const results = []

    for (const targetId of targetIds) {
      const result = await boService.associate(
        props.objectType,
        props.objectId,
        props.associationName,
        targetId,
        targetType.value
      )
      results.push({ targetId, success: result.success, message: result.message })
    }

    const failed = results.filter(r => !r.success)

    if (failed.length === 0) {
      const count = selectedItems.value.length
      if (count === 1) {
        message.success('添加成功')
      } else {
        message.success(`成功添加 ${count} 条记录`)
      }
      emit('success', selectedItems.value)
      handleClose()
    } else {
      message.warning(`成功 ${results.length - failed.length} 条，失败 ${failed.length} 条`)
    }
  } catch (e) {
    message.error('添加失败', e)
  } finally {
    submitting.value = false
  }
}

function handleClose() {
  visible.value = false
  selectedItems.value = []
}
</script>

<style scoped>
.assignment-dialog :deep(.el-dialog__header) {
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.assignment-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
}

.assignment-dialog :deep(.el-dialog__footer) {
  padding: 12px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ad-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.vh-search-bar {
  margin-bottom: 4px;
}

.ad-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px;
  color: var(--el-text-color-secondary);
}

.ad-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.ad-selected-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.ad-footer__actions {
  display: flex;
  gap: 8px;
}
</style>
