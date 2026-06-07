/**
 * useVersionContext - 产品版本上下文 Composable (单例模式)
 * 
 * 提供全局版本上下文状态管理，支持：
 * - 产品+版本级联选择
 * - 上下文过滤器（用于 API 调用）
 * - 频繁访问记录（localStorage）
 * - 上下文恢复（sessionStorage）
 * - 全局广播（provide/inject）
 * 
 * @example
 * // 在组件中使用 - 获取单例
 * const { selectedProductId, selectedVersionId, contextFilters } = useVersionContext()
 * 
 * // 提供给子组件
 * provideVersionContext()
 * 
 * // 注入到子组件
 * const { selectedProductId } = injectVersionContext()
 */

import { ref, computed, watch, provide, inject, onMounted, isRef } from 'vue'
import boService from '@/services/boService'

const VERSION_CONTEXT_KEY = 'versionContext'

const STORAGE_KEYS = {
  FREQUENT_PRODUCTS: 'bipFrequentVersions',  // 统一使用 bipFrequentVersions 键
  LAST_CONTEXT: 'lastVersionContext'
}

const MAX_FREQUENT_ITEMS = 5

let sharedContext = null
let isInitialized = false

function createVersionContext() {
  const products = ref([])
  const versions = ref([])
  const selectedProductId = ref(null)
  const selectedVersionId = ref(null)
  const selectedProduct = ref(null)
  const selectedVersion = ref(null)
  const loadingProducts = ref(false)
  const loadingVersions = ref(false)
  const error = ref(null)

  let autoLoadProducts = true
  let autoRestore = true
  let autoSave = true

  const contextFilters = computed(() => {
    const filters = {}
    if (selectedProductId.value) {
      filters.product_id = selectedProductId.value
    }
    if (selectedVersionId.value) {
      filters.version_id = selectedVersionId.value
    }
    return filters
  })

  const hasContext = computed(() => {
    return selectedProductId.value !== null && selectedVersionId.value !== null
  })

  const canSelectVersion = computed(() => {
    return selectedProductId.value !== null
  })

  async function fetchProducts() {
    loadingProducts.value = true
    error.value = null
    try {
      const result = await boService.query('product', {
        pageSize: 1000
      })
      
      const items = result.data?.items || result.data || []
      products.value = items.map(item => ({
        id: item.id,
        name: item.name || item.code || `Product ${item.id}`,
        code: item.code,
        ...item
      }))
    } catch (e) {
      console.error('[useVersionContext] Failed to fetch products:', e)
      error.value = e.message || 'Failed to fetch products'
      products.value = []
    } finally {
      loadingProducts.value = false
    }
  }

  async function fetchVersions(productId) {
    if (!productId) {
      versions.value = []
      return
    }
    
    loadingVersions.value = true
    error.value = null
    try {
      const result = await boService.query('version', {
        product_id: productId,
        pageSize: 1000
      })
      
      const items = result.data?.items || result.data || []
      versions.value = items.map(item => ({
        id: item.id,
        name: item.name || item.code || `Version ${item.id}`,
        code: item.code,
        ...item
      }))
    } catch (e) {
      console.error('[useVersionContext] Failed to fetch versions:', e)
      error.value = e.message || 'Failed to fetch versions'
      versions.value = []
    } finally {
      loadingVersions.value = false
    }
  }

  function selectProduct(product) {
    if (!product) {
      selectedProductId.value = null
      selectedProduct.value = null
      versions.value = []
      selectedVersionId.value = null
      selectedVersion.value = null
      if (autoSave) {
        saveContext()
      }
      return
    }

    selectedProductId.value = product.id
    selectedProduct.value = product
    
    fetchVersions(product.id)
    
    if (autoSave) {
      saveContext()
    }
  }

  async function selectVersion(version) {
    if (!version) {
      selectedVersionId.value = null
      selectedVersion.value = null
      if (autoSave) {
        saveContext()
      }
      return
    }

    selectedVersionId.value = version.id
    selectedVersion.value = version
    
    // 记录常用产品版本（需要同时传递产品和版本信息）
    addFrequentProduct(selectedProduct.value, version)
    
    if (autoSave) {
      saveContext()
    }
  }

  function clearContext() {
    selectedProductId.value = null
    selectedProduct.value = null
    versions.value = []
    selectedVersionId.value = null
    selectedVersion.value = null
    
    if (autoSave) {
      saveContext()
    }
  }

  const frequentLoading = ref(false)
  const favoriteVersions = ref([])

  function getFrequentProducts() {
    try {
      const stored = localStorage.getItem(STORAGE_KEYS.FREQUENT_PRODUCTS)
      if (!stored) return []
      return JSON.parse(stored)
    } catch (e) {
      return []
    }
  }

  function addFrequentProduct(product, version) {
    if (!product || !version) return
    
    try {
      const frequent = getFrequentProducts()
      // 移除相同产品版本的旧记录
      const filtered = frequent.filter(p => !(p.productId === product.id && p.versionId === version.id))
      // 添加新记录到开头
      filtered.unshift({
        productId: product.id,
        productName: product.name,
        versionId: version.id,
        versionName: version.name,
        lastAccessTime: Date.now()
      })
      
      const trimmed = filtered.slice(0, MAX_FREQUENT_ITEMS)
      localStorage.setItem(STORAGE_KEYS.FREQUENT_PRODUCTS, JSON.stringify(trimmed))
    } catch (e) {
      console.warn('[useVersionContext] Failed to add frequent product:', e)
    }
  }

  async function loadFavoriteVersions() {
    frequentLoading.value = true
    try {
      const records = getFrequentProducts()
      if (records.length === 0) {
        favoriteVersions.value = []
        return
      }
      // 用已加载的 products 数据 enrich
      const enriched = records.slice(0, MAX_FREQUENT_ITEMS).map(record => {
        const product = products.value.find(p => p.id === record.productId)
        return {
          ...record,
          productName: product?.name || record.productName
        }
      })
      favoriteVersions.value = enriched
    } catch (e) {
      console.error('[useVersionContext] Error loading favorite versions:', e)
      favoriteVersions.value = getFrequentProducts().slice(0, MAX_FREQUENT_ITEMS)
    } finally {
      frequentLoading.value = false
    }
  }

  function saveContext() {
    try {
      const context = {
        productId: selectedProductId.value,
        versionId: selectedVersionId.value
      }
      sessionStorage.setItem(STORAGE_KEYS.LAST_CONTEXT, JSON.stringify(context))
    } catch (e) {
      console.warn('[useVersionContext] Failed to save last context:', e)
    }
  }

  function restoreLastContext() {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEYS.LAST_CONTEXT)
      if (!stored) return false
      
      const context = JSON.parse(stored)
      if (!context.productId) return false
      
      return context
    } catch (e) {
      return false
    }
  }

  async function restoreContext() {
    if (!autoRestore) return

    const urlProductId = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('productId')
      : null
    const urlVersionId = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('versionId')
      : null

    if (urlProductId || urlVersionId) {
      await fetchProducts()

      let product = null
      if (urlProductId) {
        product = products.value.find(p => p.id === Number(urlProductId))
        if (product) {
          selectProduct(product)
        }
      }

      if (urlVersionId) {
        if (product) {
          await fetchVersions(product.id)
        }
        const targetVersionId = Number(urlVersionId)
        let version = versions.value.find(v => v.id === targetVersionId)
        if (!version && product) {
          try {
            const result = await boService.read('version', targetVersionId)
            const verData = result.data || result
            if (verData && verData.id) {
              await fetchVersions(product.id)
              version = versions.value.find(v => v.id === targetVersionId)
            }
          } catch (e) {
            console.warn('[useVersionContext] Failed to fetch version from URL:', e)
          }
        }
        if (version) {
          selectVersion(version)
        }
      }
      return
    }
    
    const savedContext = restoreLastContext()
    if (!savedContext) return
    
    await fetchProducts()
    
    const product = products.value.find(p => p.id === savedContext.productId)
    if (product) {
      selectProduct(product)
      
      if (savedContext.versionId) {
        await fetchVersions(product.id)
        const version = versions.value.find(v => v.id === savedContext.versionId)
        if (version) {
          selectVersion(version)
        }
      }
    }
  }

  let mounted = false

  function init() {
    if (mounted) return
    mounted = true
    
    if (autoLoadProducts) {
      fetchProducts()
    }
    if (autoRestore) {
      restoreContext()
    }
  }

  return {
    products,
    versions,
    selectedProductId,
    selectedVersionId,
    selectedProduct,
    selectedVersion,
    loadingProducts,
    loadingVersions,
    error,
    contextFilters,
    hasContext,
    canSelectVersion,
    fetchProducts,
    fetchVersions,
    selectProduct,
    selectVersion,
    clearContext,
    getFrequentProducts,
    addFrequentProduct,
    loadFavoriteVersions,
    favoriteVersions,
    frequentLoading,
    restoreContext,
    init,
    setAutoLoadProducts: (value) => { autoLoadProducts = value },
    setAutoRestore: (value) => { autoRestore = value },
    setAutoSave: (value) => { autoSave = value }
  }
}

export function useVersionContext(options = {}) {
  if (!sharedContext) {
    sharedContext = createVersionContext()
  }
  
  if (options.autoLoadProducts !== undefined) {
    sharedContext.setAutoLoadProducts(options.autoLoadProducts)
  }
  if (options.autoRestore !== undefined) {
    sharedContext.setAutoRestore(options.autoRestore)
  }
  if (options.autoSave !== undefined) {
    sharedContext.setAutoSave(options.autoSave)
  }
  
  sharedContext.init()
  
  return sharedContext
}

export function provideVersionContext(options = {}) {
  const context = useVersionContext(options)
  provide(VERSION_CONTEXT_KEY, context)
  return context
}

export function injectVersionContext() {
  const context = inject(VERSION_CONTEXT_KEY)
  if (!context) {
    console.warn('[useVersionContext] No version context provided, using default context')
    return useVersionContext()
  }
  return context
}
