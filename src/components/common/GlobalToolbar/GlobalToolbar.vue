<template>
  <div class="global-toolbar">
    <div class="gt-context">
      <template v-if="compact && hasSelection">
        <span class="gt-compact-label">{{ selectedProduct?.name }} / {{ selectedVersion?.name }}</span>
        <el-dropdown trigger="click" :teleported="false" popper-class="app-tooltip-popper" @command="handleDropdownCommand">
          <el-button type="primary" link size="small" class="gt-switch-btn">
            <el-icon><Switch /></el-icon>
            切换
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="changeProduct">切换产品</el-dropdown-item>
              <el-dropdown-item command="changeVersion">切换版本</el-dropdown-item>
              <el-dropdown-item divided command="clear">清除选择</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
      <template v-else>
        <div class="gt-selector">
          <label class="gt-label">产品</label>
          <el-select
            v-model="localProductId"
            placeholder="请选择"
            :loading="loadingProducts"
            filterable
            clearable
            size="small"
            class="gt-select"
            @change="onProductChange"
          >
            <el-option
              v-for="product in products"
              :key="product.id"
              :label="product.name"
              :value="product.id"
            />
          </el-select>
        </div>
        <div class="gt-selector">
          <label class="gt-label">版本</label>
          <el-select
            v-model="localVersionId"
            placeholder="请选择"
            :loading="loadingVersions"
            :disabled="!localProductId"
            filterable
            clearable
            size="small"
            class="gt-select"
            @visible-change="onVisibleChange"
          >
            <el-option
              v-for="version in versions"
              :key="version.id"
              :label="version.name"
              :value="version.id"
            />
          </el-select>
        </div>
      </template>
    </div>

    <div class="gt-sep"></div>

    <div class="gt-actions">
      <el-tooltip content="导入" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
        <el-button size="small" :icon="Upload" :disabled="actionDisabled?.import" @click="handleAction('import')" />
      </el-tooltip>
      <el-tooltip content="导出" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
        <el-button size="small" :icon="Download" :disabled="actionDisabled?.export" @click="handleAction('export')" />
      </el-tooltip>
      <el-tooltip content="图表视图" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
        <el-button size="small" :icon="TrendCharts" :disabled="actionDisabled?.chart" @click="handleAction('chart')" />
      </el-tooltip>
      <el-tooltip content="刷新" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
        <el-button size="small" :icon="Refresh" :disabled="actionDisabled?.refresh" @click="handleAction('refresh')" />
      </el-tooltip>
    </div>

    <el-dialog v-model="showChangeDialog" :title="changeDialogType === 'product' ? '切换产品' : '切换版本'" width="400px">
      <el-select
        v-if="changeDialogType === 'product'"
        v-model="dialogSelectValue"
        placeholder="请选择产品"
        filterable
        style="width: 100%"
      >
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select
        v-else
        v-model="dialogSelectValue"
        placeholder="请选择版本"
        filterable
        style="width: 100%"
      >
        <el-option v-for="v in versions" :key="v.id" :label="v.name" :value="v.id" />
      </el-select>
      <template #footer>
        <el-button @click="showChangeDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmChange">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Upload, Download, TrendCharts, Refresh, Switch } from '@element-plus/icons-vue'
import { useVersionContext } from '@/composables/useVersionContext'

const props = defineProps({
  compact: {
    type: Boolean,
    default: true
  },
  autoLoad: {
    type: Boolean,
    default: true
  },
  actionDisabled: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['change', 'action'])

const versionContext = useVersionContext({ autoLoadProducts: props.autoLoad })

const {
  products,
  versions,
  selectedProductId,
  selectedVersionId,
  selectedProduct,
  selectedVersion,
  loadingProducts,
  loadingVersions,
  fetchProducts,
  selectProduct,
  selectVersion,
  clearContext
} = versionContext

const localProductId = ref(selectedProductId.value)
const localVersionId = ref(selectedVersionId.value)
const showChangeDialog = ref(false)
const changeDialogType = ref('product')
const dialogSelectValue = ref(null)

const hasSelection = computed(() => !!selectedProductId.value && !!selectedVersionId.value)

watch(() => selectedVersionId.value, (val) => {
  localVersionId.value = val
}, { immediate: true })

watch(() => selectedProductId.value, (val) => {
  localProductId.value = val
})

watch(localVersionId, (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
    const version = versions.value.find(v => v.id === newVal)
    if (version) {
      selectVersion(version)
    }
    emit('change', { productId: selectedProductId.value, versionId: newVal })
  }
}, { immediate: false })

function onProductChange(productId) {
  if (!productId) {
    selectProduct(null)
    emit('change', { productId: null, versionId: null })
    return
  }
  const product = products.value.find(p => p.id === productId)
  if (product) {
    selectProduct(product)
  }
  emit('change', { productId, versionId: null })
}

function onVisibleChange(visible) {
  if (!visible && localVersionId.value) {
    const version = versions.value.find(v => v.id === localVersionId.value)
    if (version) {
      selectVersion(version)
    }
    emit('change', { productId: selectedProductId.value, versionId: localVersionId.value })
  }
}

function handleDropdownCommand(command) {
  if (command === 'changeProduct') {
    changeDialogType.value = 'product'
    dialogSelectValue.value = selectedProductId.value
    showChangeDialog.value = true
  } else if (command === 'changeVersion') {
    changeDialogType.value = 'version'
    dialogSelectValue.value = selectedVersionId.value
    showChangeDialog.value = true
  } else if (command === 'clear') {
    clearContext()
    localProductId.value = null
    localVersionId.value = null
    emit('change', { productId: null, versionId: null })
  }
}

function confirmChange() {
  if (changeDialogType.value === 'product') {
    const product = products.value.find(p => p.id === dialogSelectValue.value)
    if (product) {
      selectProduct(product)
      localProductId.value = dialogSelectValue.value
      localVersionId.value = null
    }
  } else {
    const version = versions.value.find(v => v.id === dialogSelectValue.value)
    if (version) {
      selectVersion(version)
      localVersionId.value = dialogSelectValue.value
    }
  }
  showChangeDialog.value = false
  emit('change', { productId: selectedProductId.value, versionId: selectedVersionId.value })
}

function handleAction(action) {
  emit('action', action)
}

defineExpose({
  fetchProducts,
  clearContext,
  selectedProductId,
  selectedVersionId,
  products,
  versions
})
</script>

<style scoped>
.global-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 40px;
}

.gt-context {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-compact-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.gt-switch-btn {
  margin-left: 4px;
}

.gt-selector {
  display: flex;
  align-items: center;
  gap: 6px;
}

.gt-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.gt-select {
  width: 140px;
}

.gt-sep {
  width: 1px;
  height: 20px;
  background: #dcdfe6;
  margin: 0 8px;
}

.gt-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.gt-actions .el-button {
  padding: 6px 8px;
}
</style>
