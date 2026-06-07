<template>
  <div class="version-context-selector">
    <div class="selector-row">
      <label class="selector-label">产品</label>
      <el-select
        v-model="localProductId"
        placeholder="请选择产品"
        :loading="loadingProducts"
        filterable
        clearable
        class="selector-select"
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

    <div class="selector-row">
      <label class="selector-label">版本</label>
      <el-select
        v-model="localVersionId"
        placeholder="请选择版本"
        :loading="loadingVersions"
        :disabled="!localProductId"
        filterable
        clearable
        class="selector-select"
        @change="onVersionChange"
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

    <div v-if="showClearButton && hasContext" class="selector-row">
      <el-button
        type="text"
        size="small"
        @click="onClear"
      >
        清除选择
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useVersionContext } from '@/composables/useVersionContext'

const props = defineProps({
  showClearButton: {
    type: Boolean,
    default: true
  },
  autoLoad: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits([
  'update:productId',
  'update:versionId',
  'change',
  'product-change',
  'version-change'
])

const versionContext = useVersionContext({ autoLoadProducts: props.autoLoad })
const { addFrequentProduct } = versionContext

const {
  products,
  versions,
  selectedProductId,
  selectedVersionId,
  selectedProduct,
  selectedVersion,
  loadingProducts,
  loadingVersions,
  hasContext,
  canSelectVersion,
  contextFilters,
  fetchProducts,
  selectProduct,
  selectVersion,
  clearContext
} = versionContext

const localProductId = ref(selectedProductId.value)
const localVersionId = ref(selectedVersionId.value)

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
      const product = products.value.find(p => p.id === selectedProductId.value)
      if (product) {
        addFrequentProduct(product, version)
      }
    }
    emit('change', { productId: selectedProductId.value, versionId: newVal })
  }
}, { immediate: false })

function onProductChange(productId) {
  if (!productId) {
    selectProduct(null)
    emit('product-change', null)
    emit('change', { productId: null, versionId: null })
    emit('update:productId', null)
    emit('update:versionId', null)
    return
  }

  const product = products.value.find(p => p.id === productId)
  if (product) {
    selectProduct(product)
  }
  
  emit('product-change', productId)
  emit('change', { productId, versionId: null })
  emit('update:productId', productId)
  emit('update:versionId', null)
}

function onVersionChange(versionId) {
  if (!versionId) {
    selectVersion(null)
    emit('version-change', null)
    emit('change', { productId: localProductId.value, versionId: null })
    emit('update:versionId', null)
    return
  }

  const version = versions.value.find(v => v.id === versionId)
  if (version) {
    selectVersion(version)
    // 记录常用产品版本
    const product = products.value.find(p => p.id === localProductId.value)
    if (product) {
      addFrequentProduct(product, version)
    }
  }
  
  emit('version-change', versionId)
  emit('change', { productId: localProductId.value, versionId })
  emit('update:versionId', versionId)
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

function onClear() {
  clearContext()
  localProductId.value = null
  localVersionId.value = null
  emit('change', { productId: null, versionId: null })
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
.version-context-selector {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.selector-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}

.selector-select {
  min-width: 200px;
  width: 200px;
}

@media (max-width: 768px) {
  .version-context-selector {
    flex-direction: column;
    align-items: flex-start;
  }

  .selector-select {
    width: 100%;
    min-width: unset;
  }
}
</style>
