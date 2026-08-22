/**
 * useChartPreview - 图表数据预览 composable
 *
 * 所属模块：嵌入式图表视图（Phase 4）
 *
 * 主要功能：
 *   - 基于 chartDataStore 预加载的全量数据
 *   - 通过 filterFlattenData 前端过滤（0 网络延迟）
 *   - 监听 versionId 变化时重新预加载
 *   - 监听 scopeIds 变化时重新过滤（仅前端计算，不发请求）
 *
 * 契约：见 chart-data-flow-and-interaction-upgrade.md §5.6 + §5.10.3 ⑤
 *
 * 数据流：
 *   1. versionId 变化 → chartDataStore.preload(versionId)
 *   2. scopeIds 变化 → filterFlattenData(fullData, scopeIds)
 *   3. rawData = filteredData（供 useReactiveRenderer 消费）
 *
 * 错误处理（§5.10.4 ②）：
 *   - preload 失败 → log.error + chartStore.preloadFailed=true
 *   - 不阻塞 EmbeddedChartView（list 视图独立 fetchPreviewData）
 *   - 首次切图表时检测 preloadFailed → 降级到懒加载（直接 fetchPreviewData(versionId, hierarchyFilter)）
 *
 * @param {Ref<number|string>} versionId
 * @param {Ref<Object>} scopeIds - useMultiObjectPage.scopeIds
 * @returns {{
 *   rawData: Ref<Object|null>,    // 过滤后的扁平数据
 *   loading: Ref<boolean>,        // 预加载中
 *   error: Ref<Error|null>,       // 预加载错误
 *   reload: () => Promise<void>,  // 强制重新预加载
 *   usingFallback: Ref<boolean>  // 是否降级到懒加载
 * }}
 */
import { ref, watch, computed } from 'vue'
import { useChartDataStore } from '@/stores/chartDataStore'
import { filterFlattenData } from '@/services/filterFlattenData'
import { buildPreviewDataFromArchData } from '@/services/archDataConverter'
import { buildHierarchyFilterFromScope } from '@/services/scopeToFilter'

export function useChartPreview(versionId, scopeIds) {
  const chartStore = useChartDataStore()

  // ============================================================
  // State
  // ============================================================
  const rawData = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const usingFallback = ref(false)

  // ============================================================
  // 预加载全量数据
  // ============================================================
  async function preloadData(force = false) {
    if (!versionId.value) {
      rawData.value = null
      return
    }

    loading.value = true
    error.value = null

    try {
      // 调用 chartDataStore.preload（带 TTL 缓存）
      // 注: preload 失败会抛错，由 catch 处理
      const previewData = await chartStore.preload(versionId.value, force)

      if (previewData) {
        // [FIX 2026-07-27] chartDataStore.preload 现在直接调 fetchPreviewData，
        //   返回的 previewData 已经是 { domains, subDomains, serviceModules, businessObjects, relationships, centerScope }
        //   扁平结构 + camelCase FK 字段 (domainId/subDomainId/serviceModuleId)
        const flattenData = {
          domains: previewData.domains || [],
          subDomains: previewData.subDomains || [],
          serviceModules: previewData.serviceModules || [],
          businessObjects: previewData.businessObjects || [],
          relationships: previewData.relationships || [],
          centerScope: previewData.centerScope || []
        }
        console.log('[useChartPreview] first bo keys:', Object.keys(flattenData.businessObjects[0] || {}))
        console.log('[useChartPreview] flattenData keys/len:', {
          domains: flattenData.domains?.length || 0,
          subDomains: flattenData.subDomains?.length || 0,
          serviceModules: flattenData.serviceModules?.length || 0,
          businessObjects: flattenData.businessObjects?.length || 0,
          relationships: flattenData.relationships?.length || 0
        })

        // 应用 scopeIds 过滤（前端 0 网络延迟）
        console.log('[useChartPreview] scopeIds:', JSON.stringify(scopeIds.value))
        applyScopeFilter(flattenData)
        console.log('[useChartPreview] after filter rawData keys/len:', rawData.value ? {
          domains: rawData.value.domains?.length || 0,
          subDomains: rawData.value.subDomains?.length || 0,
          serviceModules: rawData.value.serviceModules?.length || 0,
          businessObjects: rawData.value.businessObjects?.length || 0,
          relationships: rawData.value.relationships?.length || 0
        } : null)
      } else {
        rawData.value = null
      }
    } catch (err) {
      console.error('[useChartPreview] preloadData failed:', err)
      error.value = err
      // 降级链路 §5.10.4 ②: preload 失败 → 降级到懒加载
      await fallbackToLazyLoad()
    } finally {
      loading.value = false
    }
  }

  /**
   * 降级到懒加载（直接 fetchPreviewData with hierarchyFilter）
   *
   * 使用场景：
   *   - chartDataStore.preload 失败
   *   - 用户手动触发 reload 但 preload 仍失败
   */
  async function fallbackToLazyLoad() {
    if (!versionId.value) return

    usingFallback.value = true
    console.warn('[useChartPreview] Fallback to lazy load (preload failed)')

    try {
      const hierarchyFilter = buildHierarchyFilterFromScope(scopeIds.value)
      const previewData = await buildPreviewDataFromArchData(null, versionId.value, hierarchyFilter)

      // [FIX 2026-07-27] previewData 已是扁平结构，直接使用
      const flattenData = {
        domains: previewData.domains || [],
        subDomains: previewData.subDomains || [],
        serviceModules: previewData.serviceModules || [],
        businessObjects: previewData.businessObjects || [],
        relationships: previewData.relationships || [],
        centerScope: previewData.centerScope || []
      }

      // 懒加载模式：previewData 已按 hierarchyFilter 过滤，无需再 filterFlattenData
      rawData.value = flattenData
      error.value = null  // 懒加载成功，清空错误
    } catch (lazyErr) {
      console.error('[useChartPreview] Lazy load also failed:', lazyErr)
      error.value = lazyErr
      rawData.value = null
    }
  }

  /**
   * 应用 scopeIds 过滤（前端 0 网络延迟）
   *
   * 注: 此函数只在 preload 成功后调用（懒加载模式不需要，因为已用 hierarchyFilter 过滤）
   */
  function applyScopeFilter(fullFlattenData) {
    if (!fullFlattenData) {
      rawData.value = null
      return
    }

    // 调用 filterFlattenData 纯函数（前端过滤）
    const filtered = filterFlattenData(fullFlattenData, scopeIds.value)
    rawData.value = filtered
  }

  /**
   * 重新过滤（仅 scopeIds 变化时调用，0 网络延迟）
   */
  function refilter() {
    // 只在 preload 成功（非降级模式）时执行
    if (usingFallback.value) {
      // 降级模式：scopeIds 变化需要重新懒加载
      fallbackToLazyLoad()
      return
    }

    // 正常模式：从 chartStore.fullData 重新过滤
    if (chartStore.fullData) {
      // [FIX 2026-07-27] 直接用扁平字段，不再调 previewDataToFlatten
      const flattenData = {
        domains: chartStore.fullData.domains || [],
        subDomains: chartStore.fullData.subDomains || [],
        serviceModules: chartStore.fullData.serviceModules || [],
        businessObjects: chartStore.fullData.businessObjects || [],
        relationships: chartStore.fullData.relationships || [],
        centerScope: chartStore.fullData.centerScope || []
      }

      applyScopeFilter(flattenData)
    }
  }

  /**
   * 强制重新预加载（用户手动点"刷新"按钮）
   */
  async function reload() {
    usingFallback.value = false
    await preloadData(true)
  }

  // ============================================================
  // Watch 层
  // ============================================================

  // 监听 versionId 变化 → 重新预加载（含清理旧数据）
  watch(versionId, (newVal, oldVal) => {
    if (newVal !== oldVal) {
      // 版本切换：清理旧数据，重新预加载
      chartStore.clear()
      rawData.value = null
      usingFallback.value = false
      preloadData()
    }
  }, { immediate: false })

  // 监听 scopeIds 变化 → 重新过滤（仅前端计算，0 网络延迟）
  // 注：deep: true 因为 scopeIds 是 reactive 对象
  watch(scopeIds, () => {
    refilter()
  }, { deep: true })

  // ============================================================
  // 初始化：onMounted 时预加载
  // ============================================================
  // 注：使用方 EmbeddedChartView 需在 onMounted 中调用 preloadData()
  //     这里不自动调用，避免重复加载（如果 EmbeddedChartView 也调用）

  return {
    rawData,
    loading,
    error,
    reload,
    usingFallback,
    // 暴露内部方法供 EmbeddedChartView 在 onMounted 调用
    preloadData,
    refilter
  }
}
