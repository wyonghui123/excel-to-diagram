import { ref, computed, watch } from 'vue'
import boService from '@/services/boService'

export function useValueHelp(valueHelpConfig, options = {}) {
  const optionsList = ref([])
  const loading = ref(false)
  const error = ref(null)
  const displayValue = ref('')

  const source = computed(() => valueHelpConfig?.source || {})
  const behavior = computed(() => valueHelpConfig?.behavior || {})
  const presentation = computed(() => valueHelpConfig?.presentation || {})

  // 初始 options：优先使用行为配置的 initial_options（用于在 value help 异步加载前显示当前值）
  // [FIX 2026-06-14] 保存为 pinnedOptions，loadOptions 后必须合并回来
  // 场景: 详情页编辑态下, initial_options 含当前值 (例 domain_id=1, "采购管理")
  // 但 value-help API 按 created_at desc 返回前 200 条, 老数据 id=1 不在结果中
  // 不合并会导致 el-select 找不到 value=1 的 option, 显示原始 ID "1"
  const pinnedOptions = ref([])
  if (Array.isArray(behavior.value.initial_options) && behavior.value.initial_options.length > 0) {
    pinnedOptions.value = behavior.value.initial_options.map(opt => ({
      value: opt.value,
      display: opt.display || String(opt.value),
      code: opt.code || '',
      extra: {},
      __pinned: true  // 标记, 调试可见
    }))
    optionsList.value = [...pinnedOptions.value]
  }

  const sourceType = computed(() => source.value.type || 'enum')
  const sourceId = computed(() => {
    if (sourceType.value === 'enum') return source.value.enum_type_id || ''
    if (sourceType.value === 'bo') return source.value.target_bo || ''
    if (sourceType.value === 'custom') return source.value.endpoint || ''
    return ''
  })

  const sourceConfigParams = computed(() => {
    const src = source.value
    const params = {}
    if (src.value_field) params.value_field = src.value_field
    if (src.display_field) params.display_field = src.display_field
    if (src.code_field) params.code_field = src.code_field
    if (src.value_filter && Object.keys(src.value_filter).length > 0) {
      params.value_filter = src.value_filter
    }
    if (src.hierarchy && Object.keys(src.hierarchy).length > 0) {
      params.hierarchy = src.hierarchy
    }
    // [V1.2.1 2026-06-16] 传递 apply_target_permissions 参数
    // 跨域关系创建的级联字段 ValueHelp 需要跳过 dim scope 过滤
    if (src.apply_target_permissions !== undefined) {
      params.apply_target_permissions = src.apply_target_permissions
    }
    return params
  })

  let debounceTimer = null

  // 计算有效的 search_fields：
  // 优先使用 behavior.search_fields，如果为空则回退到 code_field 和 display_field
  const effectiveSearchFields = computed(() => {
    const explicit = behavior.value.search_fields
    if (explicit && explicit.length > 0) {
      return explicit
    }
    // 回退：使用 code_field 和 display_field 作为默认搜索字段
    const defaults = []
    if (source.value.code_field) defaults.push(source.value.code_field)
    if (source.value.display_field && source.value.display_field !== source.value.code_field) {
      defaults.push(source.value.display_field)
    }
    return defaults
  })

  async function loadOptions(search = '', params = {}) {
    const minLen = behavior.value.min_search_length || 0
    // 空 search 时不受 min_search_length 限制（用于预加载全部 options，让本地 filterable 工作）
    if (minLen > 0 && search.length > 0 && search.length < minLen) {
      return
    }

    if (!sourceId.value) {
      return
    }

    // 空搜索时优先显示最近使用的选项
    if (!search && behavior.value.enable_recent !== false) {
      const recentItems = getRecentItems()
      if (recentItems.length > 0) {
        // 标记最近使用的选项
        const markedRecent = recentItems.map(item => ({ ...item, isRecent: true }))
        // [FIX] 不要在 await 前直接覆盖 optionsList，否则切领域后会闪一下属于旧领域的最近项。
        // 先 loading=true 标记正在加载，等后端按 filter 返回后再 set。
        optionsList.value = []
        loading.value = true
        error.value = null

        try {
          const response = await boService.searchValueHelp(sourceType.value, sourceId.value, {
            search: '',
            search_fields: effectiveSearchFields.value.join(','),
            page: 1,
            pageSize: params.pageSize || presentation.value.page_size || 15,
            filters: params.filters || {},
            ...sourceConfigParams.value,
          })

          if (response.success && response.data) {
            const allItems = response.data.data || []
            // [FIX] 用后端 filter 结果做 intersection——只保留属于当前 parent context 的最近项。
            // localStorage 里的 markedRecent 不带 version/parent 上下文，无脑 prepend 会污染下拉
            // （切领域后看到旧领域的子领域）。
            const allValues = new Set(allItems.map(item => String(item.value)))
            const validRecent = markedRecent.filter(r => allValues.has(String(r.value)))
            const validRecentValues = new Set(validRecent.map(r => String(r.value)))
            const regularItems = allItems.filter(item => !validRecentValues.has(String(item.value)))
            // [FIX 2026-06-14] 追加 pinnedOptions (详情页编辑态当前值的占位 option)
            // 确保当前值的 option 在下拉列表中, 避免 el-select 显示原始 ID
            const regularValues = new Set(regularItems.map(item => String(item.value)))
            const pinnedNotInResult = pinnedOptions.value.filter(
              p => !regularValues.has(String(p.value))
                && !validRecentValues.has(String(p.value))
            )
            optionsList.value = [...pinnedNotInResult, ...validRecent, ...regularItems]
          }
        } catch (e) {
        // 如果加载失败，兜底显示当前 markedRecent 防止完全空白（用户至少能看到上次用过的）
        // 但这是异常路径，正常流程不会走到
        console.warn('[useValueHelp] Failed to load full options:', e)
        // [FIX 2026-06-14] 错误兜底也要保留 pinnedOptions, 避免编辑态下当前值消失
        const recentValues = new Set(markedRecent.map(r => String(r.value)))
        const pinnedNotInRecent = pinnedOptions.value.filter(p => !recentValues.has(String(p.value)))
        optionsList.value = [...pinnedNotInRecent, ...markedRecent]
      } finally {
          loading.value = false
        }
        return
      }
    }

    loading.value = true
    error.value = null

    try {
      const response = await boService.searchValueHelp(sourceType.value, sourceId.value, {
        search,
        search_fields: effectiveSearchFields.value.join(','),
        page: params.page || 1,
        pageSize: params.pageSize || presentation.value.page_size || 15,
        sort: (presentation.value.sort_by || []).map(s => `${s.field}:${s.direction || 'asc'}`).join(','),
        filters: params.filters || {},
        ...sourceConfigParams.value,
      })

      if (response.success && response.data) {
        const apiItems = response.data.data || []
        // [FIX 2026-06-14] 追加 pinnedOptions (详情页编辑态当前值的占位 option)
        // 确保当前值的 option 在下拉列表中, 避免 el-select 显示原始 ID
        const apiValues = new Set(apiItems.map(item => String(item.value)))
        const pinnedNotInResult = pinnedOptions.value.filter(p => !apiValues.has(String(p.value)))
        optionsList.value = [...pinnedNotInResult, ...apiItems]
      } else {
        error.value = response.error || response.message || 'Failed to load options'
      }
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function loadOptionsDebounced(search = '', params = {}) {
    const debounceMs = behavior.value.debounce_ms || 300
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    debounceTimer = setTimeout(() => {
      loadOptions(search, params)
    }, debounceMs)
  }

  async function resolveDisplay(value) {
    // 检查空值：null, undefined, '', 空数组
    const isEmpty = !value && value !== 0 || (Array.isArray(value) && value.length === 0)
    if (isEmpty) {
      displayValue.value = ''
      return
    }

    if (!sourceId.value) {
      displayValue.value = String(value)
      return
    }

    try {
      const response = await boService.resolveValueHelp(sourceType.value, sourceId.value, value, sourceConfigParams.value)
      if (response.success && response.data) {
        displayValue.value = response.data.display || String(value)
        const resolved = response.data
        const exists = optionsList.value.some(opt => String(opt.value) === String(resolved.value))
        if (!exists) {
          optionsList.value = [
            ...optionsList.value,
            { value: resolved.value, display: resolved.display, code: resolved.code || '', extra: {} }
          ]
        }
      } else {
        displayValue.value = String(value)
      }
    } catch (e) {
      displayValue.value = String(value)
    }
  }

  function validateInput(value) {
    if (!behavior.value.validation) return true
    if (behavior.value.binding_strength === 'loose') return true
    if (!optionsList.value.length) return true
    const strVal = String(value)
    return optionsList.value.some(opt => String(opt.value) === strVal)
  }

  function getFilterParams(formValues = {}) {
    const filters = {}
    const bindings = behavior.value.parameter_bindings || []
    for (const binding of bindings) {
      if (binding.constant) {
        filters[binding.target_field] = binding.constant
      } else if (binding.local_field && formValues[binding.local_field] !== undefined) {
        filters[binding.target_field] = formValues[binding.local_field]
      }
    }
    return filters
  }

  function isBindingSatisfied(formValues = {}) {
    const bindings = behavior.value.parameter_bindings || []
    for (const binding of bindings) {
      if (binding.required && !binding.constant) {
        if (!formValues[binding.local_field]) {
          return false
        }
      }
    }
    return true
  }

  const outMappings = computed(() => {
    return behavior.value.out_mappings || []
  })

  // 最近使用功能
  const RECENT_MAX_ITEMS = 3
  const recentKey = computed(() => `recent_value_help_${sourceId.value}`)

  function getRecentItems() {
    try {
      const stored = localStorage.getItem(recentKey.value)
      return stored ? JSON.parse(stored) : []
    } catch (e) {
      console.warn('[useValueHelp] Failed to get recent items:', e)
      return []
    }
  }

  function saveRecentItem(item) {
    try {
      const recent = getRecentItems()
      const filtered = recent.filter(r => r.value !== item.value)
      const updated = [item, ...filtered].slice(0, RECENT_MAX_ITEMS)
      localStorage.setItem(recentKey.value, JSON.stringify(updated))
    } catch (e) {
      console.warn('[useValueHelp] Failed to save recent item:', e)
    }
  }

  function applyOutMappings(selectedItem, formValues) {
    if (!outMappings.value.length || !selectedItem) return {}

    const updates = {}
    const sourceData = {
      value: selectedItem.value,
      display: selectedItem.display,
      code: selectedItem.code,
      ...(selectedItem.extra || {})
    }

    for (const mapping of outMappings.value) {
      const sourceValue = sourceData[mapping.value_help_field]
      if (sourceValue !== undefined) {
        updates[mapping.local_field] = sourceValue
      }
    }

    return updates
  }

  return {
    optionsList,
    loading,
    error,
    displayValue,
    sourceType,
    sourceId,
    loadOptions,
    loadOptionsDebounced,
    resolveDisplay,
    validateInput,
    getFilterParams,
    isBindingSatisfied,
    outMappings,
    applyOutMappings,
    getRecentItems,
    saveRecentItem,
  }
}
