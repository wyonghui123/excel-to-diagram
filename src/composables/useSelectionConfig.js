/**
 * useSelectionConfig - 选中数量配置 composable (FR-008 v2)
 *
 * 配置优先级链（高 → 低）：
 * 1. 用户偏好 user_preferences.selection.max_count
 * 2. 页面级 prop :max-selection="N"
 * 3. BO YAML <bo>.selection.max_count
 * 4. 系统配置 VITE_DEFAULT_MAX_SELECTION
 * 5. 硬编码 fallback DEFAULT = 5000
 *
 * [B2-5 2026-11-13] 上限由后端 GET /api/v2/meta/selection-limit 下发并封顶，
 * 不再接受 URL ?max_selection 覆盖。
 */
import { computed, ref, reactive } from 'vue'
import { apiV2 } from '@/utils/httpClient'

export const HARD_LIMIT = 100000
export const DEFAULT_LIMIT = 5000
export const DEFAULT_WARNING_THRESHOLD = 0.8

// [B2-5 2026-11-13] 上限唯一来源 = 后端配置，前端不再解析 URL 参数。
const backendState = reactive({ maxCount: null, warningThreshold: null, loaded: false })
let backendLimitPromise = null

export function ensureSelectionLimitLoaded() {
  if (backendLimitPromise) return backendLimitPromise
  backendLimitPromise = apiV2.get('/meta/selection-limit')
    .then(res => {
      const data = res?.data || {}
      const maxCount = Number(data.max_count)
      backendState.maxCount = Number.isFinite(maxCount) && maxCount > 0 ? maxCount : null
      const threshold = Number(data.warning_threshold)
      backendState.warningThreshold = Number.isFinite(threshold) ? threshold : null
      return backendState
    })
    .catch(() => backendState)
    .finally(() => { backendState.loaded = true })
  return backendLimitPromise
}

export function _resetSelectionLimitForTest() {
  backendState.maxCount = null
  backendState.warningThreshold = null
  backendState.loaded = false
  backendLimitPromise = null
}

function clampLimit(raw) {
  return Math.max(1, Math.min(HARD_LIMIT, parseInt(raw) || DEFAULT_LIMIT))
}

function determineSource(userVal, pageVal, yamlVal, sysVal) {
  if (userVal != null) return 'user'
  if (pageVal != null) return 'page'
  if (yamlVal != null) return 'bo'
  if (sysVal != null) return 'system'
  return 'default'
}

const SOURCE_LABELS_ZH = {
  user: '用户偏好',
  page: '页面级',
  bo: 'BO YAML',
  system: '系统配置',
  default: '系统默认',
  backend: '后端配置',
}

/**
 * @param {Object} options
 * @param {number|null} options.maxSelection - 页面级 prop
 * @param {Object} options.boConfig - BO YAML 节点
 * @param {Object} options.userPreferences - 用户偏好 store
 * @returns {{
 *   finalLimit: import('vue').ComputedRef<number>,
 *   warningThreshold: import('vue').ComputedRef<number>,
 *   allowOverride: import('vue').ComputedRef<boolean>,
 *   source: import('vue').ComputedRef<string>,
 *   sourceLabel: import('vue').ComputedRef<string>,
 *   hardLimit: number,
 *   validateSelection: (currentCount: number) => {ok: boolean, action: 'proceed'|'degrade'|'warn'}
 * }}
 */
export function useSelectionConfig(options = {}) {
  const { maxSelection = null, boConfig = null, userPreferences = null } = options

  ensureSelectionLimitLoaded()

  const userVal = ref(userPreferences?.selection?.max_count ?? null)
  const sysVal = ref(import.meta?.env?.VITE_DEFAULT_MAX_SELECTION
    ? parseInt(import.meta.env.VITE_DEFAULT_MAX_SELECTION)
    : null)

  const yamlVal = computed(() => {
    if (boConfig && typeof boConfig === 'object') {
      return boConfig?.selection?.max_count ?? null
    }
    return null
  })

  const rawLimit = computed(() => {
    // 优先级链：用户 > 页面 > BO > 系统 > 默认
    const candidates = [userVal.value, maxSelection, yamlVal.value, sysVal.value]
    return candidates.find(v => v != null) ?? DEFAULT_LIMIT
  })

  const finalLimit = computed(() => {
    const raw = rawLimit.value
    const capped = backendState.maxCount != null ? Math.min(raw, backendState.maxCount) : raw
    return clampLimit(capped)
  })

  const source = computed(() =>
    backendState.maxCount != null && rawLimit.value > backendState.maxCount
      ? 'backend'
      : determineSource(userVal.value, maxSelection, yamlVal.value, sysVal.value)
  )

  const sourceLabel = computed(() => SOURCE_LABELS_ZH[source.value] || source.value)

  const warningThreshold = computed(() => {
    if (boConfig?.selection?.warning_threshold != null) {
      return boConfig.selection.warning_threshold
    }
    if (backendState.warningThreshold != null) {
      return backendState.warningThreshold
    }
    return DEFAULT_WARNING_THRESHOLD
  })

  const allowOverride = computed(() => {
    if (boConfig?.selection?.allow_override != null) {
      return boConfig.selection.allow_override
    }
    return true
  })

  function validateSelection(currentCount) {
    if (currentCount <= finalLimit.value) {
      if (currentCount > finalLimit.value * warningThreshold.value) {
        return { ok: true, action: 'warn' }
      }
      return { ok: true, action: 'proceed' }
    }
    return { ok: false, action: 'degrade' }
  }

  return {
    finalLimit,
    warningThreshold,
    allowOverride,
    source,
    sourceLabel,
    hardLimit: HARD_LIMIT,
    validateSelection,
  }
}

export default useSelectionConfig
