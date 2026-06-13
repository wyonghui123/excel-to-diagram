/**
 * useSelectionConfig - 选中数量配置 composable (FR-008 v2)
 *
 * 配置优先级链（高 → 低）：
 * 1. URL 参数 ?max_selection=N（一次性覆盖）
 * 2. 用户偏好 user_preferences.selection.max_count
 * 3. 页面级 prop :max-selection="N"
 * 4. BO YAML <bo>.selection.max_count
 * 5. 系统配置 VITE_DEFAULT_MAX_SELECTION
 * 6. 硬编码 fallback DEFAULT = 5000
 *
 * 默认决策（2026-06-12 确认）：
 * - HARD_LIMIT = 100000
 * - warning_threshold = 0.8
 * - URL key = `max_selection`
 * - YAML 节点位置 = `<bo>.selection.max_count`
 */
import { computed, ref, onMounted } from 'vue'

export const HARD_LIMIT = 100000
export const DEFAULT_LIMIT = 5000
export const DEFAULT_WARNING_THRESHOLD = 0.8
export const URL_PARAM_KEY = 'max_selection'

function parseUrlParam(key) {
  if (typeof window === 'undefined') return null
  try {
    const params = new URLSearchParams(window.location.search)
    const v = params.get(key)
    if (v == null) return null
    const n = parseInt(v)
    return Number.isFinite(n) && n > 0 ? n : null
  } catch (e) {
    return null
  }
}

function clampLimit(raw) {
  return Math.max(1, Math.min(HARD_LIMIT, parseInt(raw) || DEFAULT_LIMIT))
}

function determineSource(urlVal, userVal, pageVal, yamlVal, sysVal) {
  if (urlVal != null) return 'url'
  if (userVal != null) return 'user'
  if (pageVal != null) return 'page'
  if (yamlVal != null) return 'bo'
  if (sysVal != null) return 'system'
  return 'default'
}

const SOURCE_LABELS_ZH = {
  url: 'URL 参数',
  user: '用户偏好',
  page: '页面级',
  bo: 'BO YAML',
  system: '系统配置',
  default: '系统默认',
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

  const urlVal = ref(parseUrlParam(URL_PARAM_KEY))
  const userVal = ref(userPreferences?.selection?.max_count ?? null)
  const sysVal = ref(import.meta?.env?.VITE_DEFAULT_MAX_SELECTION
    ? parseInt(import.meta.env.VITE_DEFAULT_MAX_SELECTION)
    : null)

  // Listen to URL changes (e.g., user navigates with different ?max_selection)
  if (typeof window !== 'undefined') {
    onMounted(() => {
      const handler = () => {
        urlVal.value = parseUrlParam(URL_PARAM_KEY)
      }
      window.addEventListener('popstate', handler)
      // Optional: cleanup on unmount
    })
  }

  const yamlVal = computed(() => {
    if (boConfig && typeof boConfig === 'object') {
      return boConfig?.selection?.max_count ?? null
    }
    return null
  })

  const finalLimit = computed(() => {
    // 优先级链：URL > 用户 > 页面 > BO > 系统 > 默认
    const candidates = [urlVal.value, userVal.value, maxSelection, yamlVal.value, sysVal.value]
    const raw = candidates.find(v => v != null) ?? DEFAULT_LIMIT
    return clampLimit(raw)
  })

  const source = computed(() =>
    determineSource(urlVal.value, userVal.value, maxSelection, yamlVal.value, sysVal.value)
  )

  const sourceLabel = computed(() => SOURCE_LABELS_ZH[source.value] || source.value)

  const warningThreshold = computed(() => {
    if (boConfig?.selection?.warning_threshold != null) {
      return boConfig.selection.warning_threshold
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
