/**
 * useUiMeta.js - 聚合 UI 元数据 Composable（T13-3）
 *
 * 单次加载 ui-meta，提供 form/detail 索引；objectType 支持字符串或 ref。
 * 缓存 / 并发去重 / schema_version 失效由 metaService.getUiMeta 负责。
 */

import { ref, shallowRef, computed, unref } from 'vue'
import metaService from '@/services/metaService'

export function useUiMeta(objectTypeRef) {
  const meta = shallowRef(null)
  const loading = ref(false)
  const error = ref(null)

  async function load(force = false) {
    const type = unref(objectTypeRef)
    if (!type) return null
    loading.value = true
    error.value = null
    try {
      meta.value = await metaService.getUiMeta(type, { force })
      return meta.value
    } catch (e) {
      error.value = e
      meta.value = null // 不提供残缺兜底，交给调用方降级
      return null
    } finally {
      loading.value = false
    }
  }

  const fieldIndex = computed(() =>
    Object.fromEntries((meta.value?.form?.fields || []).map(f => [f.key, f]))
  )
  const sectionIndex = computed(() =>
    Object.fromEntries([...(meta.value?.form?.sections || []), ...(meta.value?.detail?.sections || [])]
      .map(s => [s.key, s]))
  )

  return { meta, loading, error, load, fieldIndex, sectionIndex }
}