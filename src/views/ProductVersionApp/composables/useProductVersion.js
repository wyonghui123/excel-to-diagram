/**
 * useProductVersion - 产品版本 Composable (v2 API)
 * 
 * 提供产品版本的 CRUD 操作，使用 v2 API
 * 适配 ProductVersionApp 页面
 */

import { ref } from 'vue'
import { boService } from '@/services/boService'

let _lastSelectedProductId = null

export function useProductVersion() {
  const products = ref([])
  const versions = ref([])
  const selectedProduct = ref(null)
  const loading = ref(false)

  async function fetchProducts() {
    loading.value = true
    try {
      const result = await boService.query('product', {
        pageSize: 1000,
        filters: { is_active: true }
      })
      if (result.success) {
        products.value = result.data?.items || result.data || []
      }
    } catch (e) {
      console.error('Failed to fetch products:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchVersions(productId) {
    if (!productId) {
      versions.value = []
      return
    }
    loading.value = true
    try {
      const result = await boService.query('version', {
        pageSize: 1000,
        filters: { product_id: productId, is_active: true }
      })
      if (result.success) {
        versions.value = result.data?.items || result.data || []
      }
    } catch (e) {
      console.error('Failed to fetch versions:', e)
    } finally {
      loading.value = false
    }
  }

  async function createProduct(data) {
    const result = await boService.create('product', data)
    if (result.success) {
      await fetchProducts()
      return result
    }
    throw new Error(result.message || '创建产品失败')
  }

  async function updateProduct(id, data) {
    const result = await boService.update('product', id, data)
    if (result.success) {
      await fetchProducts()
      return result
    }
    throw new Error(result.message || '更新产品失败')
  }

  async function deleteProduct(id) {
    const result = await boService.delete('product', id)
    if (result.success) {
      await fetchProducts()
      if (selectedProduct.value?.id === id) {
        _lastSelectedProductId = null
        selectedProduct.value = null
        versions.value = []
      }
      return result
    }
    throw new Error(result.message || '删除产品失败')
  }

  async function createVersion(data) {
    const result = await boService.create('version', data)
    if (result.success) {
      await fetchVersions(data.product_id)
      return result
    }
    throw new Error(result.message || '创建版本失败')
  }

  async function updateVersion(id, data) {
    const result = await boService.update('version', id, data)
    if (result.success) {
      if (selectedProduct.value) {
        await fetchVersions(selectedProduct.value.id)
      }
      return result
    }
    throw new Error(result.message || '更新版本失败')
  }

  async function deleteVersion(id) {
    const result = await boService.delete('version', id)
    if (result.success) {
      if (selectedProduct.value) {
        await fetchVersions(selectedProduct.value.id)
      }
      return result
    }
    throw new Error(result.message || '删除版本失败')
  }

  function selectProduct(product) {
    selectedProduct.value = product
    _lastSelectedProductId = product?.id || null
    if (product) {
      fetchVersions(product.id)
    } else {
      versions.value = []
    }
  }

  useProductVersion._lastSelectedProductId = _lastSelectedProductId

  return {
    products,
    versions,
    selectedProduct,
    loading,
    fetchProducts,
    fetchVersions,
    createProduct,
    updateProduct,
    deleteProduct,
    createVersion,
    updateVersion,
    deleteVersion,
    selectProduct,
    get lastSelectedProductId() { return _lastSelectedProductId }
  }
}

useProductVersion._lastSelectedProductId = _lastSelectedProductId
