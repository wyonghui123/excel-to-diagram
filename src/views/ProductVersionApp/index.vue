<template>
  <div class="product-version-app">

    <div class="pv-layout">
      <!-- 左侧产品列表 -->
      <aside class="pv-sidebar">
        <AppInput
          v-model="searchKeyword"
          type="search"
          placeholder="搜索产品..."
          clearable
        />
        <AppButton variant="primary" size="sm" @click="openCreateProductDialog">
          + 新增产品
        </AppButton>

        <nav class="pv-product-list">
          <button
            v-for="product in filteredProducts"
            :key="product.id"
            :class="['pv-product-item', { active: selectedProductId === product.id }]"
            @click="selectProduct(product)"
          >
            <span class="product-name">{{ product.name }}</span>
            <span class="product-code">{{ product.code }}</span>
          </button>
        </nav>

        <EmptyState v-if="!loading && filteredProducts.length === 0" type="folder" description="暂无产品" />
      </aside>

      <!-- 右侧版本详情 -->
      <main class="pv-main">
        <template v-if="selectedProduct">
          <header class="pv-detail-header">
            <h3>{{ selectedProduct.name }}</h3>
            <p class="product-desc">{{ selectedProduct.description || '暂无描述' }}</p>
            <div class="header-actions">
              <AppButton variant="text" size="sm" @click="openProductHistoryDialog">
                变更历史
              </AppButton>
              <AppButton variant="text" size="sm" @click="openEditProductDialog">
                编辑
              </AppButton>
              <AppButton variant="text" danger size="sm" @click="deleteProduct(selectedProduct)">
                删除
              </AppButton>
            </div>
          </header>

          <section class="version-section">
            <div class="section-header">
              <h4>版本列表</h4>
              <AppButton variant="primary" size="sm" @click="openCreateVersionDialog">
                + 新增版本
              </AppButton>
            </div>

            <VersionTable
              :versions="filteredVersions"
              :loading="versionLoading"
              @edit="openEditVersionDialog"
              @delete="deleteVersion"
              @history="openChangeHistoryDialog"
            />
          </section>
        </template>

        <EmptyState v-else type="folder" description="请从左侧选择一个产品" />
      </main>
    </div>

    <!-- 产品表单对话框 -->
    <ProductFormDialog
      v-model:visible="showFormDialog"
      :product="editingProduct"
      @save="onProductSaved"
    />

    <!-- 版本表单对话框 -->
    <VersionFormDialog
      v-model:visible="showVersionDialog"
      :version="editingVersion"
      :product="selectedProduct"
      @save="onVersionSaved"
    />

    <!-- 变更历史对话框 -->
    <ChangeHistoryDialog
      v-model:visible="showChangeHistoryDialog"
      :object-type="historyObjectType"
      :object-id="historyObjectId"
      :target-name="historyTargetName"
      @close="showChangeHistoryDialog = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useMessage } from '@/composables/useMessage'
import { boService } from '@/services/boService'
import AppHeader from '@/components/common/AppHeader.vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppInput from '@/components/common/AppInput/AppInput.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import VersionTable from './components/VersionTable.vue'
import ProductFormDialog from './components/ProductFormDialog.vue'
import VersionFormDialog from './components/VersionFormDialog.vue'
import ChangeHistoryDialog from './components/ChangeHistoryDialog.vue'

const router = useRouter()
const authStore = useAuthStore()
const { success: toastSuccess, error: toastError } = useMessage()

const loading = ref(false)
const versionLoading = ref(false)
const products = ref([])
const versions = ref([])
const selectedProductId = ref(null)
const selectedVersionId = ref(null)
const searchKeyword = ref('')
const showFormDialog = ref(false)
const showVersionDialog = ref(false)
const showChangeHistoryDialog = ref(false)
const selectedVersionForHistory = ref(null)
const historyObjectType = ref('product')
const historyObjectId = ref(null)
const historyTargetName = ref('')
const editingProduct = ref(null)
const editingVersion = ref(null)
const confirmState = ref({ visible: false, title: '', message: '', onConfirm: null })

const selectedProduct = computed(() => products.value.find(p => p.id === selectedProductId.value))

const filteredProducts = computed(() => {
  const keyword = searchKeyword.value.toLowerCase().trim()
  if (!keyword) return products.value
  return products.value.filter(p =>
    p.name.toLowerCase().includes(keyword) ||
    p.code.toLowerCase().includes(keyword)
  )
})

const filteredVersions = computed(() => {
  if (!selectedProductId.value) return []
  return versions.value.filter(v => v.product_id === selectedProductId.value)
})

function goHome() {
  router.push('/')
}

async function loadProducts() {
  loading.value = true
  try {
    const result = await boService.query('product', {
      pageSize: 1000,
      filters: { is_active: true }
    })
    if (result.success) {
      products.value = result.data?.items || result.data || []
      if (products.value.length > 0 && !selectedProductId.value) {
        selectProduct(products.value[0])
      }
    }
  } catch (e) {
    toastError('加载产品列表失败')
  } finally {
    loading.value = false
  }
}

async function loadVersions() {
  versionLoading.value = true
  try {
    const result = await boService.query('version', {
      pageSize: 1000,
      filters: { product_id: selectedProductId.value, is_active: true }
    })
    if (result.success) {
      versions.value = result.data?.items || result.data || []
    }
  } catch (e) {
    console.error('Failed to load versions:', e)
  } finally {
    versionLoading.value = false
  }
}

function selectProduct(product) {
  selectedProductId.value = product.id
  selectedVersionId.value = null
  loadVersions()
}

function handleSelectVersion(versionId) {
  selectedVersionId.value = versionId
}

function openCreateProductDialog() {
  editingProduct.value = null
  showFormDialog.value = true
}

function openEditProductDialog() {
  editingProduct.value = { ...selectedProduct.value }
  showFormDialog.value = true
}

function openCreateVersionDialog() {
  editingVersion.value = null
  showVersionDialog.value = true
}

function openEditVersionDialog(version) {
  editingVersion.value = { ...version }
  showVersionDialog.value = true
}

function openProductHistoryDialog() {
  historyObjectType.value = 'product'
  historyObjectId.value = selectedProduct.value?.id
  historyTargetName.value = selectedProduct.value?.name || ''
  showChangeHistoryDialog.value = true
}

function openChangeHistoryDialog(version) {
  selectedVersionForHistory.value = version
  historyObjectType.value = 'version'
  historyObjectId.value = version?.id
  historyTargetName.value = version?.name || version?.version_number || ''
  showChangeHistoryDialog.value = true
}

async function onProductSaved(formData) {
  try {
    let result
    if (editingProduct.value?.id) {
      result = await boService.update('product', editingProduct.value.id, formData)
    } else {
      result = await boService.create('product', formData)
    }
    if (result.success) {
      showFormDialog.value = false
      await loadProducts()
      toastSuccess('产品保存成功')
    } else {
      toastError(result.message || '保存失败')
    }
  } catch (e) {
    toastError('网络错误，请重试')
  }
}

async function onVersionSaved(formData) {
  try {
    let result
    if (editingVersion.value?.id) {
      result = await boService.update('version', editingVersion.value.id, formData)
    } else {
      result = await boService.create('version', formData)
    }
    if (result.success) {
      showVersionDialog.value = false
      await loadVersions()
      toastSuccess('版本保存成功')
    } else {
      toastError(result.message || '保存失败')
    }
  } catch (e) {
    toastError('网络错误，请重试')
  }
}

async function deleteProduct(product) {
  try {
    const result = await boService.delete('product', product.id)
    if (result.success) {
      await loadProducts()
      toastSuccess('产品删除成功')
    } else {
      toastError(result.message || '删除失败')
    }
  } catch (e) {
    toastError('网络错误，请重试')
  }
}

async function deleteVersion(version) {
  try {
    const result = await boService.delete('version', version.id)
    if (result.success) {
      await loadVersions()
      toastSuccess('版本删除成功')
    } else {
      toastError(result.message || '删除失败')
    }
  } catch (e) {
    toastError('网络错误，请重试')
  }
}

onMounted(() => {
  loadProducts()
})
</script>

<style scoped>
.product-version-app {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f7fa;
}

.pv-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.pv-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.pv-product-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}

.pv-product-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 10px 12px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  background: transparent;
  transition: background 0.2s;
  text-align: left;
  width: 100%;
}

.pv-product-item:hover {
  background: #f5f7fa;
}

.pv-product-item.active {
  background: #ecf5ff;
}

.pv-product-item .product-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.pv-product-item .product-code {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.pv-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.pv-detail-header {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.pv-detail-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #303133;
}

.product-desc {
  color: #606266;
  font-size: 14px;
  margin: 0 0 12px 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.version-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  flex: 1;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h4 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}
</style>
