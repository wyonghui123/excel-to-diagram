<template>
  <div class="global-toolbar">
    <div class="gt-context">
      <template v-if="compact && hasSelection">
        <span class="gt-compact-label">{{ selectedProduct?.name }} / {{ selectedVersion?.name }}</span>
        <el-button type="primary" link size="small" class="gt-switch-btn" @click="openSwitchDialog">
          <el-icon><Switch /></el-icon>
          切换
        </el-button>
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
        <el-button 
          size="small" 
          :icon="TrendCharts"
          :disabled="actionDisabled?.chart"
          class="gt-btn-chart"
          @click="handleAction('chart')"
        >
          图表视图
        </el-button>
      </el-tooltip>
      <el-tooltip content="刷新" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
        <el-button size="small" :icon="Refresh" :disabled="actionDisabled?.refresh" @click="handleAction('refresh')" />
      </el-tooltip>
    </div>

    <el-dialog v-model="showSwitchDialog" title="切换产品版本" width="440px" :close-on-click-modal="false">
      <div class="gt-switch-dialog">
        <div class="gt-switch-field">
          <label class="gt-switch-label">产品 <span class="gt-required">*</span></label>
          <el-select
            v-model="dialogProductId"
            placeholder="请选择产品"
            :loading="loadingProducts"
            filterable
            clearable
            style="width: 100%"
            @change="onDialogProductChange"
          >
            <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
        <div class="gt-switch-field">
          <label class="gt-switch-label">版本 <span class="gt-required">*</span></label>
          <el-select
            v-model="dialogVersionId"
            placeholder="请选择版本"
            :loading="loadingDialogVersions"
            :disabled="!dialogProductId"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option v-for="v in dialogVersions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
        </div>
      </div>
      <template #footer>
        <div class="gt-switch-footer">
          <el-button v-if="hasSelection" link type="danger" @click="clearSelection">清除选择</el-button>
          <span class="gt-switch-footer-right">
            <el-button @click="showSwitchDialog = false">取消</el-button>
            <el-button type="primary" :disabled="!dialogProductId || !dialogVersionId" @click="confirmSwitch">确定</el-button>
          </span>
        </div>
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
  fetchVersions,
  selectProduct,
  selectVersion,
  clearContext
} = versionContext

const localProductId = ref(selectedProductId.value)
const localVersionId = ref(selectedVersionId.value)
const showSwitchDialog = ref(false)
const dialogProductId = ref(null)
const dialogVersionId = ref(null)
const dialogVersions = ref([])
const loadingDialogVersions = ref(false)

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

function openSwitchDialog() {
  dialogProductId.value = selectedProductId.value
  dialogVersionId.value = selectedVersionId.value
  dialogVersions.value = versions.value ? [...versions.value] : []
  showSwitchDialog.value = true
}

async function onDialogProductChange(productId) {
  dialogVersionId.value = null
  if (!productId) {
    dialogVersions.value = []
    return
  }
  loadingDialogVersions.value = true
  try {
    await fetchVersions(productId)
    dialogVersions.value = versions.value ? [...versions.value] : []
  } finally {
    loadingDialogVersions.value = false
  }
}

async function confirmSwitch() {
  const product = products.value.find(p => p.id === dialogProductId.value)
  if (!product) {
    return
  }
  await selectProduct(product)
  const version = dialogVersions.value.find(v => v.id === dialogVersionId.value)
  if (version) {
    await selectVersion(version)
  }
  localProductId.value = dialogProductId.value
  localVersionId.value = dialogVersionId.value
  showSwitchDialog.value = false
  emit('change', { productId: selectedProductId.value, versionId: selectedVersionId.value })
}

function clearSelection() {
  clearContext()
  localProductId.value = null
  localVersionId.value = null
  dialogProductId.value = null
  dialogVersionId.value = null
  dialogVersions.value = []
  showSwitchDialog.value = false
  emit('change', { productId: null, versionId: null })
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
  gap: 8px;

  :deep(.el-button + .el-button) {
    margin-left: 0;
  }
}

.gt-actions .el-button {
  padding: 6px 8px;
  width: 32px;
  height: 32px;
  box-sizing: border-box;
  margin: 0;

  &:hover,
  &:focus,
  &:active {
    width: 32px;
    height: 32px;
    padding: 6px 8px;
    margin: 0;
    transform: none;
    box-shadow: none;
  }
}

/* 图表视图按钮 - 突出主操作 */
.gt-btn-chart {
  width: auto !important;
  min-width: 90px;
  padding: 4px 12px !important;
  background: rgba(234, 88, 12, 0.08) !important;
  border: 1px solid var(--color-primary, #ea580c) !important;
  color: var(--color-primary, #ea580c) !important;
  font-weight: 500;
  gap: 4px;

  .el-icon {
    font-size: 14px;
  }

  &:hover:not(:disabled) {
    background: var(--color-primary, #ea580c) !important;
    color: #fff !important;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

/* 切换产品版本弹窗 */
.gt-switch-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-switch-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-switch-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.gt-required {
  color: var(--color-danger, #f56c6c);
}

.gt-switch-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.gt-switch-footer-right {
  display: flex;
  gap: 8px;
}
</style>
