/**
 * 重复配置检测 Composable
 *
 * 封装 Section 1 (管理维度) 与 Section 3 (条件型权限) 重叠加检测。
 * 优先调用后端 API，后端未就绪时回退到本地计算。
 */
import { ref } from 'vue'
import { http } from '@/utils/http'

export interface OverlapRule {
  rule_id: string
  field: string
  operator: string
  value: any[]
  intersection: any[]
}

export interface Overlap {
  field: string
  source: string
  dim_scope: {
    dimension_code: string
    dimension_values: any[]
    bo_id: string | null
  }
  rules: OverlapRule[]
  count: number
}

export interface OverlapSummary {
  has_overlap: boolean
  count: number
  fields: string[]
}

export function useOverlaps(roleId: number | null) {
  const overlaps = ref<Overlap[]>([])
  const summary = ref<OverlapSummary>({ has_overlap: false, count: 0, fields: [] })
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * 加载重叠加
   */
  async function loadOverlaps(resourceType?: string) {
    if (!roleId) return
    loading.value = true
    error.value = null
    try {
      const params = resourceType ? `?resource_type=${resourceType}` : ''
      const resp = await http.get(`/api/v2/roles/${roleId}/overlaps${params}`)
      if (resp.data?.success) {
        overlaps.value = resp.data.data.overlaps || []
        summary.value = resp.data.data.summary || { has_overlap: false, count: 0, fields: [] }
      } else {
        error.value = resp.data?.error || '加载失败'
      }
    } catch (e: any) {
      error.value = e?.message || '网络错误'
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载摘要（轻量级）
   */
  async function loadSummary() {
    if (!roleId) return
    try {
      const resp = await http.get(`/api/v2/roles/${roleId}/overlaps/summary`)
      if (resp.data?.success) {
        summary.value = resp.data.data || { has_overlap: false, count: 0, fields: [] }
      }
    } catch (e: any) {
      // 静默失败，不影响主流程
      console.warn('loadOverlapSummary failed:', e)
    }
  }

  /**
   * 判断指定字段是否有重叠加
   */
  function hasOverlap(field: string): boolean {
    return summary.value.fields.includes(field)
  }

  /**
   * 获取指定字段的重叠加详情
   */
  function getOverlapForField(field: string): Overlap | undefined {
    return overlaps.value.find(o => o.field === field)
  }

  /**
   * 获取重叠加的提示文本
   */
  function getOverlapHint(field: string): string {
    const overlap = getOverlapForField(field)
    if (!overlap) return ''
    const dimVals = overlap.dim_scope.dimension_values
    return `Section 1 已配 ${overlap.dim_scope.dimension_code} = [${dimVals.join(', ')}]，Section 3 重复配置将覆盖`
  }

  return {
    overlaps,
    summary,
    loading,
    error,
    loadOverlaps,
    loadSummary,
    hasOverlap,
    getOverlapForField,
    getOverlapHint,
  }
}
