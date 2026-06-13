/**
 * useMetaList - 元数据驱动的动态列表 Composable (Element Plus 版)
 * 
 * 设计理念：
 * - 参考 Salesforce Lightning Data Service (LDS) 模式
 * - 完全复用 Element Plus 组件（el-table, el-form, el-pagination）
 * - 支持元数据驱动 + 自定义插槽的混合模式
 * 
 * 使用方式：
 * ```javascript
 * const { columns, filters, actions, data, loading, pagination,
 *         loadList, handleAction } = useMetaList('user', { mode: 'element-plus' })
 * ```
 */

import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick, shallowRef, unref } from 'vue'
import { evaluateCondition } from '@/utils/safeExpression'
import { ElMessage, ElMessageBox } from 'element-plus'
import { boService } from '@/services/boService'
import { metaService } from '@/services/metaService'
import { dateFormatService } from '@/services/DateFormatService'
import { useFieldPolicy } from './useFieldPolicy'
import { useListActionStore } from '@/stores/listActionStore'
import { suggestKeyTemplateCode as _suggestKeyTemplateCodeSvc } from '@/services/keyTemplateService'
import { saveAllDrafts as _saveAllDraftsSvc, getDraftCreates as _getDraftCreatesSvc } from '@/services/draftPersistService'
import { useBoAction } from '@/composables/useBoAction'
import { t as i18nT } from '@/i18n'
import {
  isInternalProp,
  transformFilters,
  backfillColumnFilterType,
  getDefaultFilterValues,
  addFilterParam,
  buildFilterQueryParams,
  mergeFilters,
  addExportFilterParam as _addExportFilterParamSvc
} from '@/services/filterService'
import {
  transformColumns as _transformColumnsSvc,
  inferColumnPriority as _inferColumnPrioritySvc,
  transformActions as _transformActionsSvc,
  inferActionPosition as _inferActionPositionSvc,
  mapVariant as _mapVariantSvc,
  inferColumnWidth as _inferColumnWidthSvc,
  fixDatetimeColumns as _fixDatetimeColumnsSvc,
  enrichColumnsWithFieldMeta as _enrichColumnsWithFieldMetaSvc,
  getDefaultOrdering as _getDefaultOrderingSvc,
  filterRowActions as _filterRowActionsSvc,
  inferFieldEditConfig as _inferFieldEditConfigSvc
} from '@/services/metaTransformService'

/**
 * 统一的错误处理函数
 * @param {string} context - 操作上下文描述
 * @param {Error} error - 错误对象
 * @param {Object} options - 选项 { showMessage: boolean, defaultMessage: string, t?: Function }
 */
function handleError(context, error, options = {}) {
  const { showMessage = true, defaultMessage, t = i18nT } = options

  console.error(`[useMetaList] ${context}:`, error)

  // [FIX 2026-06-08] 403 权限不足不弹错误 toast（避免无意义干扰），由页面显示权限提示
  const errorCode = error?.response?.status || error?.status || error?.code
  if (errorCode === 403) {
    return error
  }

  if (showMessage) {
    const message = error?.response?.data?.error ||
                    error?.message ||
                    error?.msg ||
                    (defaultMessage || t('metaList.loadFailed', '{context}失败', { context }))
    ElMessage.error(message)
  }

  return error
}

export function useMetaList(objectType, options = {}) {
  // [FIX] useBoAction 是工厂函数（导出的是函数本身，不是 {callPost} 对象），
  //   必须先调用 useBoAction() 才能拿到 callPost。
  //   之前 `const { callPost } = await import('@/composables/useBoAction')`
  //   是错的 —— import() 返回的是模块对象 { useBoAction, default }，
  //   解构出 callPost === undefined，传给 service 后报
  //   `callPost is not a function`。
  //   useBoAction 只依赖 httpClient + authStore，与 useMetaList 无循环依赖，
  //   故可在 setup 上下文直接静态 import + 顶层调用。
  //
  // [v3 决策 2026-06-13] 验证: useBoAction() 是纯函数工厂 (无 setup 副作用，
  //   无 watch/computed，无 onMounted)，N 个 MetaListPage 实例的工厂调用
  //   **无性能成本**。FR-018 惰性化不适用 (昨晚 spec 假设错误)。
  //   真正的前置应是 useFieldPolicy.autoLoad() 集成 (见下)。
  const { callPost } = useBoAction()

  // ======== 配置项 ========
  const config = {
    mode: options.mode || 'element-plus',  // 'element-plus' | 'custom'
    autoLoad: options.autoLoad !== false,   // 是否自动加载数据
    pageSize: options.pageSize || 20,
    pageSizes: options.pageSizes || null,   // 覆盖分页 size 选项列表
    debug: options.debug || false,
    // 过滤器显示模式：
    // - 'hover': SAP风格，鼠标悬停时显示（默认）
    // - 'always': 始终显示
    // - 'manual': 手动控制（需要用户点击按钮显示）
    filterDisplayMode: options.filterDisplayMode || 'hover',
    // 行可维护性：'locked' | 'extensible' | 'fully_editable' | null
    rowMutability: options.rowMutability || null,
    // 自定义数据获取器 (params) => Promise<{success, data}>
    fetcher: options.fetcher || null,
    // compact mode: 'page' | 'embedded' | 'dialog'
    displayMode: options.displayMode || 'page',
    // 列定义覆盖（embedded/dialog 生效，传入后跳过 metaService）
    columnsOverride: options.columnsOverride || null,
    // 排除的ID列表（dialog 生效）
    excludeIds: options.excludeIds || [],
    // 行唯一键
    rowKey: options.rowKey || 'id',
    // 自定义行操作按钮（embedded/dialog 生效）
    rowActionsOverride: options.rowActionsOverride || null,
    // 自定义工具栏操作按钮（embedded/dialog 生效）
    toolbarActionsOverride: options.toolbarActionsOverride || null,
    // 自定义批量操作按钮（embedded/dialog 生效）
    batchActionsOverride: options.batchActionsOverride || null
  }

  // ======== 响应式状态 ========
  
  /** 元数据原始配置 */
  const metaConfig = ref(null)
  
  /** 列定义（Element Plus el-table-column 格式） */
  const columns = ref([])
  
  /** 过滤器定义（el-form-item 格式） */
  const filterFields = ref([])

  /** API 返回的 filters 数组（包含 filter_type 等信息） */
  const apiFilterConfigs = ref([])
  
  /** 可见的过滤器字段（过滤掉 defaultVisible=false 的字段） */
  const visibleFilterFields = computed(() =>
    filterFields.value.filter(field => field.defaultVisible !== false)
  )

  // [FIX 2026-06-08] 权限不足标记：用于页面显示"无权限"提示而非空数据
  const permissionDenied = ref(false)
  
  /** 工具栏操作按钮 */
  const toolbarActions = ref([])
  
  /** 工具栏右侧操作按钮 */
  const toolbarRightActions = ref([])
  
  /** 行级操作按钮 */
  const rowActions = ref([])
  
  /** 批量操作配置 */
  const batchActions = ref([])
  
  /** 导出字段配置 */
  const exportFields = ref([])
  
  /** 导入选项配置 */
  const importOptions = ref({})
  
  /** 列表数据 */
  // [M2 PR-2.1] data 列表可能包含 1000+ 行，整个 set 替换 (data.value = ...) 而非 push/splice
  //   改 shallowRef 避免深度代理，v-for 直接消费 data.value 不受影响
  const data = shallowRef([])
  
  /** 加载状态 */
  const loading = ref(false)
  
  /** 分页信息 */
  const pagination = reactive({
    current: 1,
    pageSize: config.pageSize,
    total: 0
  })
  
  /** 带筛选条件的总数（用于导出弹窗显示"全部数据"条数） */
  const filteredTotalCount = ref(0)
  
  /** 排序信息 */
  const sortInfo = ref({
    prop: null,
    order: null  // 'ascending' | 'descending'
  })
  
  /** 过滤器值 */
  const filterValues = ref({})
  
  /** 上下文过滤条件（如父级 ID enum_type_id），重置时应保留 */
  const contextFilters = ref({})
  
  /** 表头过滤值（列级别的过滤） */
  const headerFilterValues = ref({})
  
  /** 选中的行（用于批量操作） */
  const selectedRows = shallowRef([])
  
  /** 选中的记录ID集合（跨页保留） */
  const selectedIds = ref(new Set())

  /** 是否选择了所有页 */
  const isAllPagesSelected = ref(false)

  // [FR-008 v1] 选区上限：防止跨页累积导致序列化/反序列化慢
  // 业界惯例: Gmail 模式上限 1000, Material UI DataGrid 默认 RowSpanLimit 1000
  // 1000 行足够大多数批量操作 (1000 records × 5 fields ≈ 100KB JSON, 后端 batch_delete 接受)
  const MAX_SELECTION_LIMIT = 1000

  /** 是否触发了选区上限（用于 UI 提示 + 阻止超限 selectAllPages） */
  const selectionLimitHit = ref(false)
  
  /** 导出对话框显示状态 */
  const showExportDialog = ref(false)
  
  /** 导入对话框显示状态 */
  const showImportDialog = ref(false)
  
  /** 搜索字段配置（从元数据获取） */
  const searchFields = ref([])
  
  /** 关键词搜索值 */
  const keyword = ref('')

  // ======== 计算属性 ========
  
  /**
   * 可见的列（过滤掉 visible=false 或 default_visible=false 的列）
   */
  const visibleColumns = computed(() => {
    const filtered = columns.value.filter(col =>
      col.visible !== false && col.default_visible !== false && !col.hidden_in_list
    )

    if (config.displayMode === 'page') {
      return filtered
    }

    const columnsFromProp = !!config.columnsOverride
    if (columnsFromProp) {
      return filtered
    }

    const maxPriority = config.displayMode === 'dialog' ? 'default' : 'default'

    const result = filtered.filter(col => {
      const priority = col.column_priority || _inferColumnPriority(col)
      if (maxPriority === 'default') return priority === 'required' || priority === 'default'
      return priority === 'required'
    })

    return result
  })
  
  /**
   * 总选择数量（跨页）
   */
  const totalSelectedCount = computed(() => {
    if (isAllPagesSelected.value) {
      return pagination.total
    }
    return selectedIds.value.size
  })
  
  /**
   * 当前页选中的数量
   */
  const currentPageSelectedCount = computed(() => {
    return selectedRows.value.length
  })

  /**
   * 默认排序字段（从元数据获取）
   */
  const defaultSort = computed(() => {
    if (!metaConfig.value) return undefined

    const meta = metaConfig.value
    const yamlOrd = meta.listConfig?.defaultOrdering || meta.list?.defaultOrdering || meta.defaultOrdering
    if (yamlOrd) {
      const isDesc = yamlOrd.startsWith('-')
      const prop = isDesc ? yamlOrd.slice(1) : yamlOrd
      const order = isDesc ? 'descending' : 'ascending'
      return { prop, order }
    }

    const defaultSortConfig = meta.list?.defaultSort
    if (defaultSortConfig?.field) {
      return {
        prop: defaultSortConfig.field,
        order: defaultSortConfig.order === 'desc' ? 'descending' : 'ascending'
      }
    }

    return undefined
  })

  /**
   * 分页配置（从元数据获取或使用默认值）
   */
  const paginationConfig = computed(() => {
    const metaPagination = metaConfig.value?.list?.pagination || {}
    return {
      pageSizes: config.pageSizes || metaPagination.pageSizeOptions || [10, 20, 50, 100],
      layout: 'total, sizes, prev, pager, next, jumper',
      background: true
    }
  })

  /**
   * 过滤器显示模式配置（从元数据获取或使用默认值）
   * - 'hover': SAP风格，鼠标悬停时显示过滤器图标（默认）
   * - 'always': 始终显示过滤器图标
   * - 'manual': 手动控制（需要用户点击按钮显示）
   */
  const filterDisplayModeConfig = computed(() => {
    return metaConfig.value?.list?.filterDisplayMode || config.filterDisplayMode || 'hover'
  })

  /**
   * 导出过滤器参数（与列表查询使用相同的格式）
   * 用于导出功能，确保过滤条件与列表一致
   * 
   * 注意：后端期望的格式是 { key: [value] } 数组格式
   */
  const exportFilters = computed(() => {
    const params = {}
    
    // 添加关键词搜索
    if (keyword.value && keyword.value.trim() && searchFields.value.length > 0) {
      params._search = [keyword.value.trim()]
      params._search_fields = [searchFields.value.map(f => f.field).join(',')]
    }
    
    // 添加过滤区域的条件
    Object.keys(filterValues.value)
      .filter(key => !isVueInternalProp(key))
      .forEach(key => {
        _addExportFilterParam(params, key, filterValues.value[key])
      })
    
    // 合并表头过滤条件
    Object.keys(headerFilterValues.value)
      .filter(key => !isVueInternalProp(key))
      .forEach(key => {
        _addExportFilterParam(params, key, headerFilterValues.value[key])
      })
    

    
    return params
  })

  // ======== 核心方法 ========
  
  /**
   * 初始化：加载元数据并转换格式
   * @param {Array} columnsOverride - 列定义覆盖（compact mode）
   */
  async function init(columnsOverride) {
    if (!objectType) {
      console.warn(`[useMetaList] [WARNING] objectType 为空，跳过初始化`)
      data.value = []
      pagination.total = 0
      return
    }
    boService._clearCache(objectType)
    metaService.clearCache(objectType)
    try {
      const effectiveColumns = columnsOverride || config.columnsOverride
      if (effectiveColumns) {
        columns.value = _transformColumns(effectiveColumns)
        // 先加载元数据，确保 metaConfig.value 可用
        await _loadMetaConfig()
        // [FIX-2026-06-08] _loadMetaConfig() 内部会调 _transformMetaToComponentFormat()
        //   无条件用 metaConfig 的 columns 覆盖 columns.value, 导致 columnsOverride 失效。
        //   重新应用 columnsOverride 保证 compact 模式自定义列生效。
        columns.value = _transformColumns(effectiveColumns)
        // 使用 metaConfig 来富化 columns
        if (metaConfig.value) {
          _enrichColumnsWithFieldMeta(metaConfig.value.list || metaConfig.value)
        }
        _fixDatetimeColumns()
        if (config.rowActionsOverride) {
          rowActions.value = config.rowActionsOverride
        }
        try {
          if (batchActions.value.length === 0 && (metaConfig.value?.list?.batch_actions || metaConfig.value?.list?.batchActions)) {
            const listConfig = metaConfig.value.list
            batchActions.value = _transformActions(listConfig.batch_actions || listConfig.batchActions)
          }
        } catch (e) {
          // ignore
        }
        if (config.autoLoad || columns.value.length > 0) {
          await loadList()
        }
        return
      }

      await _loadMetaConfig()
      
      // [DECORATIVE] [NEW] v1.3 / FR-6.1: 激活 field-policies API
      if (objectType && autoLoad) {
        autoLoad(objectType, 'read').catch(e => {
          console.warn('[useMetaList] autoLoad field-policies failed:', e)
        })
      }

      const hasColumns = columns.value && columns.value.length > 0
      const shouldAutoLoad = config.autoLoad || hasColumns
      if (shouldAutoLoad) {
        if (hasColumns) {
          await loadList()
        } else {
          console.warn(`[useMetaList] [WARNING] columns为空，跳过loadList。metaConfig.list:`, JSON.stringify(metaConfig.value?.list?.columns || metaConfig.value?.list?.tableColumns || null))
          data.value = []
          pagination.total = 0
        }
      } else {
        data.value = []
        pagination.total = 0
      }
    } catch (error) {
      console.error(`[useMetaList] [X] 初始化失败 (${objectType}):`, error)
      ElMessage.error(i18nT('metaList.loadListConfigFailed', '加载列表配置失败'))
    }
  }

  /**
   * 加载列表数据
   * @param {Object} extraParams - 额外查询参数
   */
  async function loadList(extraParams = {}) {
    if (!objectType) {
      console.warn(`[useMetaList] [WARNING] loadList: objectType 为空，跳过`)
      data.value = []
      pagination.total = 0
      loading.value = false
      return
    }
    loading.value = true
    
    try {
      const params = _buildQueryParams(extraParams)

      const result = await (config.fetcher
        ? config.fetcher({ page: pagination.current, pageSize: pagination.pageSize, ...params })
        : boService.query(objectType, params))
      if (result?.data) {
      }

      // [FIX 2026-06-08] 403 权限不足：静默处理，不刷控制台错误
      if (!result.success && result.httpStatus === 403) {
        permissionDenied.value = true
        data.value = []
        pagination.total = 0
        return
      }

      if (result.success) {
        let rawData = result.data
        
        if (rawData && rawData.items && Array.isArray(rawData.items)) {
          data.value = rawData.items
          pagination.total = rawData.total || rawData.items.length

          // 存储 API 返回的 filters 数组（包含 filter_type 等信息）
          if (rawData.filters && Array.isArray(rawData.filters)) {
            apiFilterConfigs.value = rawData.filters
            // 重新回填 filter_type
            if (metaConfig.value) {
              _backfillColumnFilterType(metaConfig.value.list || metaConfig.value)
            }
          }
        } else if (Array.isArray(rawData)) {
          data.value = rawData
          pagination.total = rawData.length
        } else {
          data.value = []
          pagination.total = 0
          console.warn('[useMetaList] [WARNING] 无法识别的数据格式:', typeof rawData, rawData ? (Array.isArray(rawData) ? `数组长度${rawData.length}` : Object.keys(rawData).slice(0,5)) : null)
        }

        permissionDenied.value = false


        
        _restoreSelectionState()
      } else {
        console.warn(`[useMetaList] [WARNING] boService.query 返回 success=false:`, result.message || '无消息')
        handleError('加载数据', new Error(result.message || '加载数据失败'), { showMessage: false })
      }
    } catch (error) {
      console.error(`[useMetaList] [X] loadList 异常:`, error)
      handleError('加载数据', error)
      data.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取带筛选条件的总数（用于导出弹窗）
   * 使用当前列表的筛选条件，获取符合条件的数据总数
   */
  async function loadTotalCount() {
    try {
      const params = _buildQueryParams({
        page: 1,
        page_size: 1
      })
      
      const result = await boService.query(objectType, params)
      
      if (result.success) {
        const rawData = result.data
        if (rawData && rawData.total !== undefined) {
          filteredTotalCount.value = rawData.total
        } else if (Array.isArray(rawData)) {
          filteredTotalCount.value = rawData.length
        }
      }
    } catch (error) {
      console.error(`[useMetaList] 获取总数失败 (${objectType}):`, error)
    }
  }

  /**
   * 处理操作按钮点击
   * @param {Object} actionInfo - 操作信息 { action, row }
   */
  async function handleAction(actionInfo) {
    const { action, row, rows } = actionInfo
    
    try {
      // 处理导入导出操作（通用逻辑）
      if (action.key === 'export') {
        handleBatchExport()
        return
      }
      
      if (action.key === 'import') {
        handleBatchImport()
        return
      }
      
      // 处理批量删除操作（批量删除有自己的确认对话框，不要在这里再确认）
      if (action.key === 'batch_delete') {
        await handleBatchDelete()
        return
      }
      
      // 处理批量移除操作（由 AssociationSection 处理）
      if (action.key === 'batch_unassign') {
        return
      }
      
      // 如果有确认对话框配置
      if (action.confirmMessage && !await _showConfirm(action)) {
        return  // 用户取消
      }
      
      // 触发自定义事件（由页面组件处理具体逻辑）
      emitActionEvent(action, row)
    } catch (error) {
      handleError(`执行操作 ${action.key}`, error)
    }
  }

  /**
   * 处理工具栏按钮点击
   * @param {Object} action - 操作配置
   */
  async function handleToolbarAction(action) {
    // 在 inline 编辑模式下，create 按钮应该触发内联新增行
    if (inlineEditMode.value && 
        (action.key === 'create' || action.key === '新建' || action.key === 'new')) {
      addNewRow()
      return
    }
    
    await handleAction({ action })
  }

  /**
   * 处理批量操作按钮点击
   * @param {Object} action - 操作配置
   */
  async function handleBatchAction(action) {
    if (selectedRows.value.length === 0) {
      ElMessage.warning(i18nT('metaList.selectRowsFirst', '请先选择要操作的数据'))
      return
    }
    
    await handleAction({ action, rows: selectedRows.value })
  }

  /**
   * 处理过滤器变更
   * @param {Object} values - 新的过滤器值
   */
  function handleFilter(values) {
    filterValues.value = { ...values }
    pagination.current = 1  // 重置到第一页
    loadList()
  }

  /**
   * 处理搜索（快捷方法）
   */
  function handleSearch() {
    handleFilter(filterValues.value)
  }

  /**
   * 处理排序变更
   * @param {Object} sort - 排序信息 { prop, order }
   */
  function handleSortChange(sort) {
    // [FIX 2026-06-08] 排序变更时重置到第 1 页
    sortInfo.value = sort
    pagination.current = 1
    loadList()
  }

  /**
   * 处理页码变更
   * @param {Number} page - 新页码
   */
  function handlePageChange(page) {
    pagination.current = page
    loadList()
  }

  /**
   * 处理每页条数变更
   * @param {Number} size - 新的每页条数
   */
  function handlePageSizeChange(size) {
    pagination.pageSize = size
    pagination.current = 1
    loadList()
  }

  /**
   * 处理行选择变更（批量操作用）
   * @param {Array} rows - 选中的行
   */
  function handleSelectionChange(rows) {
    selectedRows.value = rows
    
    const rowKey = config.rowKey || 'id'
    const currentPageIds = new Set(data.value.map(row => row[rowKey]))
    const newSet = new Set([...selectedIds.value].filter(id => !currentPageIds.has(id)))
    
    rows.forEach(row => {
      if (row[rowKey]) {
        newSet.add(row[rowKey])
      }
    })
    selectedIds.value = newSet
  }

  /**
   * 处理批量删除
   */
  async function handleBatchDelete() {
    if (selectedIds.value.size === 0) {
      ElMessage.warning(i18nT('metaList.selectDeleteFirst', '请选择要删除的记录'))
      return
    }

    const count = selectedIds.value.size

    try {
      await ElMessageBox.confirm(
        i18nT('metaList.confirmDeleteMessage', '确定要删除选中的 {count} 条记录吗？', { count }),
        i18nT('metaList.confirmDeleteTitle', '确认删除'),
        {
          confirmButtonText: i18nT('common.confirm', '确定'),
          cancelButtonText: i18nT('common.cancel', '取消'),
          type: 'warning'
        }
      )
      
      const idsToDelete = Array.from(selectedIds.value)

      const result = await boService.batchDelete(objectType, idsToDelete)

      if (result.success) {
        const deletedCount = result.success_count || idsToDelete.length
        const successMsg = i18nT('metaList.deleteSuccess', '成功删除 {count} 条记录', { count: deletedCount })
        // [FIX 2026-06-12 v4] 用户反馈成功 message 不明显 (ElMessage 顶部 3s 自动消失容易错过)
        // 改用三重保险: ElNotification (显眼长条) + ElMessage (快速反馈) + console.log
        console.log('[useMetaList] 批量删除成功:', successMsg, result)
        ElNotification({
          title: i18nT('common.delete', '删除成功'),
          message: successMsg,
          type: 'success',
          duration: 4500,
          position: 'top-right',
          showClose: true,
        })
        ElMessage.success(successMsg)
        clearAllSelection()
        await loadList()
      } else {
        // [FIX 2026-06-12 v2] 真实错误信息优先级:
        // 1) result.message (顶层 message)
        // 2) result.data.results[].message (batch-delete 207 把每条记录的 message 放在这里)
        // 3) result.errors (string[]) — 这是技术错误码, 不是中文
        // 4) 兜底 "删除失败"
        let errorMsg = result.message
        if (!errorMsg) {
          const resultsArr = result.data?.results || []
          const messagesFromResults = resultsArr
            .map(r => r?.message)
            .filter(Boolean)
          if (messagesFromResults.length) {
            errorMsg = messagesFromResults.join('; ')
          }
        }
        if (!errorMsg && Array.isArray(result.errors) && result.errors.length) {
          errorMsg = result.errors
            .map(e => (typeof e === 'string' ? e : e?.message || JSON.stringify(e)))
            .join('; ')
        }
        if (!errorMsg) errorMsg = i18nT('metaList.deleteFailed', '删除失败')

        // [FIX 2026-06-12 v3] 用户反馈 el-message 不够明显, 改用三重保险:
        // 1) ElNotification 右上角长条 (4.5s, 显眼, 不被遮)
        // 2) ElMessage 顶部 (3s, 快速反馈)
        // 3) console.error (开发者工具可见)
        // 之前用 ElMessage.error(errorMsg) 单一途径, 顶部 3s 自动消失, 用户容易错过
        console.error('[useMetaList] 批量删除失败:', errorMsg, result)
        ElNotification({
          title: i18nT('metaList.deleteFailedTitle', '删除失败'),
          message: errorMsg,
          type: 'error',
          duration: 6000,  // 6 秒, 比默认 4.5s 更长
          position: 'top-right',
          showClose: true,
        })
        ElMessage({
          message: errorMsg,
          type: 'error',
          duration: 6000,
          showClose: true,
        })
      }
    } catch (error) {
      if (error !== 'cancel') {
        console.error('[useMetaList] 批量删除失败:', error)
        ElMessage.error(error.message || i18nT('metaList.deleteFailed', '删除失败'))
      }
    }
  }

  /**
   * 处理批量导出
   */
  async function handleBatchExport() {
    try {
      await loadTotalCount()
      showExportDialog.value = true
    } catch (error) {
      handleError('打开导出对话框', error, { showMessage: false })
      showExportDialog.value = true
    }
  }

  /**
   * 处理批量导入
   */
  function handleBatchImport() {
    try {
      showImportDialog.value = true
    } catch (error) {
      handleError('打开导入对话框', error, { showMessage: false })
      showImportDialog.value = true
    }
  }
  
  /**
   * 处理导出成功
   * 注意：成功消息已在 ExportDialog 中显示，这里只处理关闭对话框
   */
  function handleExportSuccess(result) {
    showExportDialog.value = false
  }
  
  /**
   * 处理导入成功
   */
  async function handleImportSuccess(result) {
    const results = result?.results || {}
    let totalCount = 0
    for (const typeResult of Object.values(results)) {
      totalCount += (typeResult.success || 0) + (typeResult.deleted || 0)
    }
    ElMessage.success(i18nT('metaList.importSuccess', '导入完成，共处理 {count} 条数据', { count: totalCount }))
    showImportDialog.value = false
    await loadList()
  }
  
  /**
   * 设置上下文过滤条件（如父级 enum_type_id）
   * 这些条件在重置时会被保留
   * @param {Object} context - 上下文过滤条件
   */
  function setContextFilters(context = {}) {
    Object.keys(contextFilters.value).forEach(key => {
      if (!(key in context)) {
        delete filterValues.value[key]
      }
    })
    contextFilters.value = { ...context }
    Object.entries(context).forEach(([key, value]) => {
      if (!isVueInternalProp(key) && value !== undefined && value !== null && value !== '') {
        filterValues.value[key] = value
      }
    })
  }
  
  /**
   * 重置所有过滤条件和排序（保留默认值，如父级上下文 enum_type_id）
   */
  function resetFilters() {
    // 重置用户修改的过滤条件，但保留默认值和上下文过滤条件
    const defaults = {}
    filterFields.value.forEach(field => {
      if (field.defaultValue !== undefined && field.defaultValue !== '') {
        defaults[field.key] = field.defaultValue
      }
    })
    // 合并上下文过滤条件（如父级 enum_type_id）
    Object.assign(defaults, contextFilters.value)
    filterValues.value = defaults
    headerFilterValues.value = {}  // 重置表头过滤
    sortInfo.value = { prop: null, order: null }
    pagination.current = 1
    loadList()
  }
  
  /**
   * 处理表头过滤变更
   * @param {string} field - 字段键名
   * @param {*} value - 过滤值
   */
  function handleHeaderFilter(field, value) {
    if (value === null || value === undefined || value === '') {
      delete headerFilterValues.value[field]
    } else {
      headerFilterValues.value[field] = value
    }
    pagination.current = 1  // 重置到第一页
    loadList()
  }
  
  /**
   * 重置特定字段的表头过滤
   * @param {string} field - 字段键名
   */
  function resetHeaderFilter(field) {
    delete headerFilterValues.value[field]
    loadList()
  }
  
  /**
   * 选择当前页所有行
   */
  function selectAllCurrentPage() {
    if (!data.value || data.value.length === 0) return

    const rowKey = config.rowKey || 'id'
    const newSet = new Set(selectedIds.value)
    data.value.forEach(row => {
      if (row[rowKey]) {
        newSet.add(row[rowKey])
      }
    })
    // [FR-008 v1] 选区上限保护
    if (newSet.size > MAX_SELECTION_LIMIT) {
      // 截断到上限, 标记 hit
      const truncated = new Set([...newSet].slice(0, MAX_SELECTION_LIMIT))
      selectedIds.value = truncated
      selectionLimitHit.value = true
      ElMessage.warning(
        i18nT('metaList.selectionLimitHit', '选中数量超过上限 {limit} 条, 已截断。请减少选区或分批操作。', { limit: MAX_SELECTION_LIMIT })
      )
    } else {
      selectedIds.value = newSet
    }

    selectedRows.value = [...data.value]
  }

  /**
   * 选择所有页（参考 Gmail 模式）
   */
  function selectAllPages() {
    isAllPagesSelected.value = true

    const rowKey = config.rowKey || 'id'
    const newSet = new Set(selectedIds.value)
    data.value.forEach(row => {
      if (row[rowKey]) {
        newSet.add(row[rowKey])
      }
    })
    // [FR-008 v1] 选区上限保护: Gmail 模式理论上选所有页, 但要防止 pagination.total 异常
    if (newSet.size > MAX_SELECTION_LIMIT) {
      const truncated = new Set([...newSet].slice(0, MAX_SELECTION_LIMIT))
      selectedIds.value = truncated
      selectionLimitHit.value = true
      ElMessage.warning(
        i18nT('metaList.selectionLimitHit', '选中数量超过上限 {limit} 条, 已截断。请减少选区或分批操作。', { limit: MAX_SELECTION_LIMIT })
      )
    } else {
      selectedIds.value = newSet
    }

    selectedRows.value = [...data.value]
  }
  
  /**
   * 清除所有选择
   */
  function clearAllSelection() {
    // 创建新的空 Set 以触发响应式更新
    selectedIds.value = new Set()
    selectedRows.value = []
    isAllPagesSelected.value = false
    // [FR-008 v1] 重置上限 hit 标志
    selectionLimitHit.value = false
  }

  /**
   * 刷新当前列表（保持当前页和过滤条件）
   */
  async function refresh() {
    boService.clearCache(objectType)
    await loadList()
  }

  /**
   * 获取行的可用操作（考虑权限和条件）
   * @param {Object} row - 当前行数据
   * @returns {Array} 可用的行级操作
   */
  function getRowActions(row) {
    return _filterRowActionsSvc(rowActions.value, row, objectType, config.rowMutability, _checkPermission, _evaluateCondition)
  }

  // ======== 内部方法 ======

  /**
   * 恢复当前页的选择状态（跨页选择保留）
   * @private
   */
  function _restoreSelectionState() {
    if (selectedIds.value.size === 0 && !isAllPagesSelected.value) {
      selectedRows.value = []
      return
    }
    
    // 如果选择了所有页，当前页全部选中
    if (isAllPagesSelected.value) {
      selectedRows.value = [...data.value]
      return
    }
    
    // 根据 selectedIds 恢复当前页的选择状态
    const restoredRows = data.value.filter(row => 
      row.id && selectedIds.value.has(row.id)
    )
    
    selectedRows.value = restoredRows
  }

  /**
   * 加载元数据配置
   * @private
   */
  async function _loadMetaConfig() {
    if (!objectType) {
      console.warn('[useMetaList] [WARNING] _loadMetaConfig: objectType 为空')
      return
    }
    try {
      const result = await metaService.getViewConfig(objectType)
      
      if (result.success && result.data) {
        metaConfig.value = result.data
        
        _transformMetaToComponentFormat()
        return
      } else {
        console.warn(`[useMetaList] [WARNING] 无法加载 ${objectType} 的元数据: success=${result?.success}, data存在=${!!result?.data}, message=${result?.message || 'none'}`)
      }
    } catch (e) {
      console.error(`[useMetaList] [X] 加载元数据失败 (${objectType}):`, e)
    }
    
    console.warn(`[useMetaList] [WARNING] 元数据加载失败，使用空配置回退`)
    metaConfig.value = {
      list: {
        columns: [],
        actions: [],
        filters: []
      }
    }
    
    _transformMetaToComponentFormat()
  }

  /**
   * 将元数据转换为组件格式
   * @private
   */
  function _transformMetaToComponentFormat() {
    if (!metaConfig.value) {
      console.error('[useMetaList] [X] metaConfig 为空，无法转换')
      return
    }
    
    const listConfig = metaConfig.value.list || metaConfig.value
    
    // 转换列定义
    if (listConfig.tableColumns || listConfig.columns) {
      columns.value = _transformColumns(listConfig.tableColumns || listConfig.columns, listConfig)
    } else {
      console.warn('[useMetaList] [WARNING] 未找到列定义 (tableColumns/columns)')
    }
    
    // 转换过滤器
    if (listConfig.filterFields || listConfig.filters) {
      filterFields.value = _transformFilters(listConfig.filterFields || listConfig.filters)
    }
    
    // 用后端 filters 数组的类型信息回填 columns 的 filter_type
    // 后端 _auto_generate_filters 已正确推断类型（date_range/number_range/select），
    // 但这些信息只在 filters 数组中，columns 的 filter_type 为空
    _backfillColumnFilterType(listConfig)
    
    // 用字段元数据信息回填 columns 的 businessKey / valueHelp 等
    _enrichColumnsWithFieldMeta(listConfig)
    
    // 最终修正：datetime 后缀字段无条件设为 datetime 类型
    // （_enrichColumnsWithFieldMeta 可能会用空 type 覆盖 _transformColumns 的设置）
    _fixDatetimeColumns()
    
    // 转换操作按钮
    if (listConfig.actions) {
      const allActions = _transformActions(listConfig.actions)
      toolbarActions.value = allActions.filter(a => a.position === 'toolbar')
      const EXCLUDED_ROW_ACTIONS = ['view', 'detail', 'edit', 'update']
      rowActions.value = allActions.filter(a => 
        (a.position === 'row' || !a.position) && 
        !EXCLUDED_ROW_ACTIONS.some(ex => a.key?.toLowerCase().includes(ex))
      )
    }

    if (config.rowActionsOverride) {
      rowActions.value = unref(config.rowActionsOverride)
    }

    const toolbarOverride = unref(config.toolbarActionsOverride)
    // 空数组 [] 应该被视为显式清空操作，而不是走默认逻辑
    if (toolbarOverride !== undefined && toolbarOverride !== null) {
      toolbarActions.value = toolbarOverride
    } else {
      // 转换头部操作（只有在没有 override 时才处理）
      if (listConfig.headerActions) {
        const transformed = _transformActions(listConfig.headerActions)
        // 分离 toolbar-left 和 toolbar-right 的按钮
        const leftActions = transformed.filter(a => a.position === 'toolbar' || !a.position)
        const rightActions = transformed.filter(a => a.position === 'toolbar-right')
        
        // toolbar-left 按钮放左边
        toolbarActions.value = [
          ...leftActions.map(a => ({ ...a, position: 'toolbar' })),
          ...toolbarActions.value
        ]
        
        // toolbar-right 按钮单独存储
        toolbarRightActions.value = rightActions.map(a => ({ ...a, position: 'toolbar-right' }))
      }
    }
    
    // 加载批量操作配置
    if (listConfig.batch_actions || listConfig.batchActions) {
      batchActions.value = _transformActions(listConfig.batch_actions || listConfig.batchActions)
    }
    
    // 应用批量操作覆盖
    const batchOverride = unref(config.batchActionsOverride)
    // 空数组 [] 应该被视为显式清空操作，而不是走默认逻辑
    if (batchOverride !== undefined && batchOverride !== null) {
      batchActions.value = batchOverride
    }
    
    // 加载导出字段配置
    if (listConfig.exportOptions?.includeFields) {
      exportFields.value = listConfig.exportOptions.includeFields.map(field => {
        const col = columns.value.find(c => c.key === field)
        return {
          key: field,
          label: col?.label || col?.title || field
        }
      })
    }
    
    // 加载导入选项配置
    if (listConfig.importOptions) {
      importOptions.value = listConfig.importOptions
    }
    
    // 根据 import_export.import_enabled 自动添加导入按钮
    const importExport = metaConfig.value.import_export || metaConfig.value.ui_view_config?.import_export
    if (importExport?.import_enabled) {
      const hasImportAction = toolbarActions.value.some(a => 
        a.key?.toLowerCase() === 'import' || a.key?.toLowerCase().includes('import')
      )
      if (!hasImportAction) {
        toolbarActions.value.push({
          key: 'import',
          label: '导入',
          icon: 'upload',
          variant: 'default',
          position: 'toolbar'
        })
      }
    }
    
    // 根据 import_export.export_enabled 自动添加导出按钮（如果不存在）
    if (importExport?.export_enabled !== false) {
      const hasExportAction = toolbarRightActions.value.some(a => 
        a.key?.toLowerCase() === 'export' || a.key?.toLowerCase().includes('export')
      )
      if (!hasExportAction) {
        toolbarRightActions.value.push({
          key: 'export',
          label: '导出',
          icon: 'download',
          variant: 'default',
          position: 'toolbar-right'
        })
      }
    }

    // 解析 Inline Edit 配置
    _parseInlineEditConfig(listConfig)
    
    // 加载搜索字段配置（单一事实原则：从元数据获取）
    if (listConfig.searchFields && Array.isArray(listConfig.searchFields)) {
      searchFields.value = listConfig.searchFields.map(field => {
        const col = columns.value.find(c => c.key === field || c.field === field)
        return {
          field: field,
          label: col?.label || col?.title || field
        }
      })
    }
    
    // 设置默认过滤器值
    _initDefaultFilterValues()
    
    // 设置默认排序
    if (defaultSort.value) {
      sortInfo.value = defaultSort.value
    }
  }

  /**
   * 转换列定义为 Element Plus 格式
   * @private
   * @param {Array} yamlColumns - YAML 定义的列
   * @param {Object} [listConfig] - 列表配置(用于取 fields + columnOrder)
   * @returns {Array} el-table-column 配置数组
   */
  function _transformColumns(yamlColumns, listConfig) {
    // 优先使用 listConfig.fields(API 端有), 回退到 metaConfig.value.fields
    const fields = (listConfig && Array.isArray(listConfig.fields) && listConfig.fields.length > 0)
      ? listConfig.fields
      : (metaConfig.value?.fields || [])
    // 列序配置: listConfig.columnOrder → metaConfig.value.ui_view_config.list.column_order
    const columnOrder = (listConfig && listConfig.columnOrder)
      || metaConfig.value?.ui_view_config?.list?.column_order
      || {}
    return _transformColumnsSvc(yamlColumns, {
      filterDisplayMode: filterDisplayModeConfig.value,
      fields,
      columnOrder,
    })
  }

  /**
   * 自动推断列优先级（compact mode 使用）
   * - required: id、business_key、display_name 等必须展示的列
   * - default: 常规辅助列
   * - optional: datetime、系统字段等仅完整页展示的列
   * @private
   */
  function _inferColumnPriority(col) {
    return _inferColumnPrioritySvc(col)
  }

  /**
   * 转换操作按钮为统一格式
   * @private
   * @param {Array} yamlActions - YAML 定义的操作
   * @returns {Array} 统一格式 actions
   */
  function _transformActions(yamlActions) {
    return _transformActionsSvc(yamlActions)
  }

  /**
   * 智能推断操作位置（参考 SAP Fiori 和 Salesforce Lightning）
   * @private
   * @param {Object} action - 操作配置
   * @returns {String} 推断的位置：toolbar | row | batch
   */
  function _inferActionPosition(action) {
    return _inferActionPositionSvc(action)
  }

  /**
   * 映射变体名称到 Element Plus button type
   * @private
   * @param {String} variant - 原始变体名称
   * @param {String} position - 操作位置：toolbar | row | batch
   * @returns {String} Element Plus button type
   */
  function _mapVariant(variant, position = 'row') {
    return _mapVariantSvc(variant, position)
  }

  function _backfillColumnFilterType(listConfig) {
    // 优先使用 API 返回的 filters（包含正确的 filter_type）
    const apiFilters = apiFilterConfigs.value || []
    // 回退到 listConfig 中的 filters
    const configFilters = listConfig.filterFields || listConfig.filters || []
    // API filters 优先
    const rawFilters = apiFilters.length > 0 ? apiFilters : configFilters
    backfillColumnFilterType(columns.value, rawFilters)
    // 触发响应式更新 - 使用 splice 来替换整个数组
    columns.value.splice(0, columns.value.length, ...columns.value)
  }

  /**
   * 最终修正：确保所有 datetime 后缀字段 type='datetime'
   * 无论 _transformColumns 或 _enrichColumnsWithFieldMeta 如何设置
   * @private
   */
  function _fixDatetimeColumns() {
    _fixDatetimeColumnsSvc(columns.value)
  }

  /**
   * 用字段元数据信息回填 columns
   * 包括 businessKey、valueHelp 等字段级元数据
   * @private
   * @param {Object} listConfig - 列表配置（包含 fields 数组或从 metaConfig.fields 回退）
   */
  function _enrichColumnsWithFieldMeta(listConfig) {
    const fields = (listConfig.fields && listConfig.fields.length > 0)
      ? listConfig.fields
      : (metaConfig.value?.fields || [])
    columns.value = _enrichColumnsWithFieldMetaSvc(columns.value, fields, metaConfig.value)
  }

  /**
   * 根据字段类型和内容推断列宽度
   * 参考 SAP Fiori、Salesforce Lightning、Material Design 最佳实践
   * @private
   * @param {Object} col - 列配置
   * @returns {Object} { width, minWidth }
   */
  function _inferColumnWidth(col) {
    return _inferColumnWidthSvc(col)
  }

  /**
   * 转换过滤器为 el-form-item 格式
   * @private
   * @param {Array} yamlFilters - YAML 定义的过滤器
   * @returns {Array} FilterBar fields 配置
   */
  function _transformFilters(yamlFilters) {
    const result = transformFilters(yamlFilters, metaConfig.value)
    return result
  }

  /**
   * 初始化默认过滤器值
   * @private
   */
  function _initDefaultFilterValues() {
    const defaults = getDefaultFilterValues(filterFields.value)
    if (Object.keys(defaults).length > 0) {
      filterValues.value = defaults
    }
  }

  /**
   * 添加导出过滤条件到参数对象（后端期望数组格式）
   * @private
   * @param {Object} params - 参数字典
   * @param {string} key - 字段键名
   * @param {*} value - 字段值
   */
  function _addExportFilterParam(params, key, value) {
    _addExportFilterParamSvc(params, key, value, columns.value, filterFields.value, _formatDate)
  }

  /**
   * 添加过滤条件到参数对象
   * @private
   * @param {Object} params - 参数字典
   * @param {string} key - 字段键名
   * @param {*} value - 字段值
   */
  function isVueInternalProp(key) {
    return isInternalProp(key)
  }

  function _addFilterParam(params, key, value) {
    addFilterParam(params, key, value, columns.value, filterFields.value, config)
  }
  
  /**
   * 获取默认排序规则
   * @private
   * @returns {string|null} eg "-updated_at"
   */
  function _getDefaultOrdering() {
    return _getDefaultOrderingSvc(metaConfig.value)
  }
  
  /**
   * 构建查询参数
   * @private
   * @returns {Object} API 请求参数
   */
  function _buildQueryParams(extraParams = {}) {
    const params = buildFilterQueryParams({
      page: pagination.current,
      pageSize: pagination.pageSize,
      keyword: keyword.value,
      filterValues: filterValues.value,
      headerFilterValues: headerFilterValues.value,
      columns: columns.value,
      filterFields: filterFields.value,
      sortProp: sortInfo.value.prop,
      sortOrder: sortInfo.value.order,
      defaultOrdering: _getDefaultOrdering(),
      extraParams,
      debug: config.debug
    })

    if (config.excludeIds && config.excludeIds.length > 0) {
      params.exclude_ids = config.excludeIds.join(',')
    }

    return params
  }
  
  /**
   * 格式化日期为 YYYY-MM-DD HH:mm:ss 格式
   * @private
   * @param {Date|string} date - 日期
   * @param {boolean} isEndTime - 是否是结束时间（自动设置为 23:59:59）
   * @returns {string} 格式化后的日期字符串
   */
  function _formatDate(date, isEndTime = false) {
    if (!date) return ''
    const d = new Date(date)
    if (isNaN(d.getTime())) return ''
    
    if (isEndTime) {
      d.setHours(23, 59, 59, 999)
    } else {
      d.setHours(0, 0, 0, 0)
    }
    
    return formatDate(d, 'YYYY-MM-DD HH:mm:ss')
  }

  /**
   * 显示确认对话框
   * @private
   * @param {Object} action - 操作配置
   * @returns {Promise<Boolean>} 用户是否确认
   */
  async function _showConfirm(action) {
    let message = action.confirmMessage
    if (message && message.includes('{row.')) {
      // 简单的模板替换（后续可改为更强大的模板引擎）
      message = message.replace(/\{row\.(\w+)\}/g, (match, key) => {
        return selectedRows.value[0]?.[key] || ''
      })
    }
    
    try {
      await ElMessageBox.confirm(message, action.confirmTitle || i18nT('metaList.confirmTitle', '确认操作'), {
        confirmButtonText: i18nT('common.confirm', '确定'),
        cancelButtonText: i18nT('common.cancel', '取消'),
        type: action.variant === 'danger' ? 'warning' : 'info'
      })
      return true
    } catch {
      return false
    }
  }

  /**
   * 权限检查（简化版，后续集成权限系统）
   * @private
   * @param {Object} action - 操作配置
   * @returns {Boolean} 是否有权限
   */
  function _checkPermission(action) {
    if (!action.permission) return true
    
    // TODO: 集成实际的权限检查系统
    // 例如：return hasPermission(action.permission)
    return true  // 暂时返回 true
  }

  /**
   * 条件表达式评估（支持多种格式）
   * @private
   * @param {String} condition - 条件表达式
   * @param {Object} row - 当前行数据
   * @returns {Boolean} 是否满足条件
   */
  function _evaluateCondition(condition, row) {
    if (!condition) return true
    return evaluateCondition(condition, row, 'row')
  }

  /**
   * 触发操作事件（供外部监听）
   * @private
   */
  function emitActionEvent(action, row) {
    const listActionStore = useListActionStore()
    listActionStore.dispatchAction(objectType, action, row)
  }

  // ======== Inline Edit 状态和方法 ========
  
  /** Inline Edit 配置（从元数据解析） */
  const inlineEditConfig = ref({
    enabled: false,
    mode: 'quick',           // 'quick' | 'direct'
    autoSave: false,
    toolbarPosition: 'bottom'
  })
  
  /** 是否处于编辑模式 */
  const inlineEditMode = ref(false)
  
  /** 编辑中的草稿值 Map<rowId, Object<fieldName, newValue>> */
  const draftValues = ref(new Map())
  
  /** 当前正在编辑的单元格 { rowId, fieldName } */
  const editingCell = ref(null)
  
  /** 当前悬停的单元格 { rowId, fieldName } */
  const hoveredCell = ref(null)
  
  /** 是否有未保存的修改 */
  const hasUnsavedChanges = computed(() => draftValues.value.size > 0)
  
  /** FieldPolicy - 统一字段策略引擎 */
  const {
    autoLoad,         // [DECORATIVE] [NEW] v1.3 / FR-6.1
    editableMap,
    visibleMap,
    immutableMap,
    isEditable: policyIsEditable,
    isNewRowCheck,
    evaluateMutability
  } = useFieldPolicy(metaConfig, columns)
  
  /**
   * 使用 FieldPolicy 判断字段是否可编辑
   * @param {Object} row - 行数据
   * @param {string} fieldName - 字段名
   * @returns {boolean}
   */
  function isCellEditable(row, fieldName) {
    if (!inlineEditConfig.value.enabled || !inlineEditMode.value) return false
    
    // 从 columns 中获取字段配置（单一事实来源）
    const column = columns.value.find(c => c.prop === fieldName || c.name === fieldName)
    if (!column) return false
    
    // 显式设置为 editable: false 的字段不可编辑
    if (column.editable === false) return false
    
    // 字段级隐藏配置
    if (column.hidden_in_detail === true) return false
    if (column.hidden_in_form === true) return false
    
    // 判断是否是新行（新增的行）
    const isNewRow = isNewRowCheck(row)
    
    // 使用 FieldPolicy 判断（如果可用）
    // 新行：所有字段都可编辑（除了 editable: false 的）
    // 现有行：immutable 字段不可编辑
    if (!isNewRow && column.immutable === true) return false
    
    // 使用 policyIsEditable 进行更精确的判断
    const mutability = metaConfig.value?.semantics?.mutability || null
    return policyIsEditable(fieldName, row, mutability)
  }
  
  /**
   * 解析 inlineEdit 配置
   * @private
   */
  function _parseInlineEditConfig(listConfig) {
    const inlineEdit = options.inlineEdit || listConfig?.inlineEdit || {}
    
    inlineEditConfig.value = {
      enabled: inlineEdit.enabled === true,
      mode: inlineEdit.mode || 'quick',
      autoSave: inlineEdit.autoSave === true,
      toolbarPosition: inlineEdit.toolbarPosition || 'bottom'
    }
  }
  
  /**
   * 启用编辑模式
   * @param {boolean} directEdit - 是否直接进入编辑状态，编辑第一个可编辑单元格
   */
  function enableInlineEdit(directEdit = false) {
    if (!inlineEditConfig.value.enabled) return
    inlineEditMode.value = true
    
    // 直接进入编辑状态：编辑第一个可编辑单元格
    if (directEdit && data.value.length > 0) {
      const firstRow = data.value[0]
      const firstEditableField = columns.value.find(col => 
        col.prop && isCellEditable(firstRow, col.prop)
      )
      if (firstEditableField) {
        startEditCell(firstRow, firstEditableField.prop)
      }
    }
  }

  /**
   * 添加新行（用于 inline 新增）
   * @returns {Object} 新行的初始数据
   */
  /**
   * 添加新行（用于 inline 新增）
   * @param {Object} extraData - 额外数据，如关联字段
   * @returns {Object} 新行的初始数据
   */
  function addNewRow(extraData = {}) {
    const newRow = {
      _isNew: true,
      id: `__new_${Date.now()}__`
    }
    
    columns.value.forEach(col => {
      if (col.prop && col.defaultValue !== undefined) {
        newRow[col.prop] = col.defaultValue
      }
    })
    
    Object.keys(filterValues.value)
      .filter(key => !isVueInternalProp(key))
      .forEach(key => {
        if (key.endsWith('_id') && !newRow.hasOwnProperty(key)) {
          newRow[key] = filterValues.value[key]
        }
      })
    
    Object.assign(newRow, extraData)
    
    const rowDrafts = {}
    Object.keys(newRow).forEach(key => {
      if (key.startsWith('_') || key === 'id') return
      const column = columns.value.find(c => c.prop === key || c.name === key)
      if (column && !isCellEditable(newRow, key)) return
      rowDrafts[key] = newRow[key]
    })
    draftValues.value.set(newRow.id, rowDrafts)
    draftValues.value = new Map(draftValues.value)
    
    newRow._initialValues = { ...rowDrafts }
    
    data.value = [newRow, ...data.value]
    
    if (inlineEditMode.value) {
      const firstEditableField = columns.value.find(col => 
        col.prop && isCellEditable(newRow, col.prop)
      )
      if (firstEditableField) {
        nextTick(() => {
          startEditCell(newRow, firstEditableField.prop)
        })
      }
    }
    
    _suggestKeyTemplateCode(newRow)
    
    return newRow
  }
  
  async function _suggestKeyTemplateCode(newRow) {
    // 业务逻辑下沉到 keyTemplateService（PR 4）
    const result = await _suggestKeyTemplateCodeSvc(
      newRow,
      filterValues.value,
      draftValues.value,
      boService,
      config,
      isVueInternalProp
    )
    // 触发响应式更新（service 是纯函数，调用方负责）
    if (result.success && result.shouldUpdateDraft) {
      draftValues.value = new Map(draftValues.value)
    }
  }
  
  /**
   * 禁用编辑模式（会提示保存）
   */
  async function disableInlineEdit() {
    if (hasUnsavedChanges.value) {
      try {
        await ElMessageBox.confirm(
          i18nT('metaList.discardChangesMessage', '有未保存的修改，是否放弃？'),
          i18nT('metaList.discardChangesTitle', '提示'),
          { type: 'warning', confirmButtonText: i18nT('metaList.discardChangesConfirm', '放弃'), cancelButtonText: i18nT('common.cancel', '取消') }
        )
      } catch {
        return false
      }
    }
    cancelInlineEdit()
    inlineEditMode.value = false
    return true
  }
  
  /**
   * 开始编辑单元格
   */
  function startEditCell(row, fieldName) {
    editingCell.value = { rowId: row.id, fieldName }
  }
  
  /**
   * 结束当前单元格编辑
   */
  function finishEditCell(save = true) {
    if (!editingCell.value) return
    
    const { rowId, fieldName } = editingCell.value
    
    if (!save) {
      cancelCellEdit(rowId, fieldName)
    }
    
    editingCell.value = null
  }
  
  /**
   * 更新单元格草稿值
   */
  function updateDraftValue(rowId, fieldName, newValue) {
    let rowDrafts = draftValues.value.get(rowId)
    if (!rowDrafts) {
      rowDrafts = {}
      draftValues.value.set(rowId, rowDrafts)
    }
    rowDrafts[fieldName] = newValue
    
    // 触发响应式更新
    draftValues.value = new Map(draftValues.value)
  }
  
  /**
   * 取消单元格编辑
   */
  function cancelCellEdit(rowId, fieldName) {
    const rowDrafts = draftValues.value.get(rowId)
    if (rowDrafts) {
      delete rowDrafts[fieldName]
      if (Object.keys(rowDrafts).length === 0) {
        draftValues.value.delete(rowId)
      }
      draftValues.value = new Map(draftValues.value)
    }
  }
  
  /**
   * 取消所有编辑
   */
  function cancelInlineEdit() {
    const newRowsToRemove = data.value.filter(row => row._isNew === true)
    if (newRowsToRemove.length > 0) {
      newRowsToRemove.forEach(newRow => {
        draftValues.value.delete(newRow.id)
      })
      data.value = data.value.filter(row => row._isNew !== true)
    }
    draftValues.value.clear()
    draftValues.value = new Map()
    editingCell.value = null
  }
  
  /**
   * 获取所有待创建的新增行 payload（不含 id 等系统字段）
   * 供父组件收集子数据后调用 deepInsert 使用
   * @returns {Array} 待创建行的 payload 数组
   *
   * 业务逻辑下沉到 draftPersistService（PR 4）
   */
  function getDraftCreates() {
    return _getDraftCreatesSvc(draftValues.value, data.value)
  }

  /**
   * 保存所有编辑
   *
   * 业务逻辑下沉到 draftPersistService（PR 4）
   */
  async function saveDraftValues() {
    loading.value = true
    try {
      // [FIX] callPost 已在 useMetaList 顶层 setup 上下文中通过 useBoAction() 解构得到
      const result = await _saveAllDraftsSvc({
        objectType,  // objectType 是 useMetaList 形参（字符串），不是 ref，不要加 .value
        draftValues: draftValues.value,
        data: data.value,  // C2 修复：传 array 而非 ref
        callPost,
        showMessage: ElMessage,
      })

      // C2 修复：composable 负责应用 toRemove（service 不直接操作 ref）
      if (result.toRemove && result.toRemove.length > 0) {
        const toRemoveIds = new Set(
          result.toRemove.filter(r => r.removeFromData).map(r => String(r.rowId))
        )
        if (toRemoveIds.size > 0) {
          data.value = data.value.filter(row => !toRemoveIds.has(String(row.id)))
        }
      }

      if (result.success) {
        draftValues.value.clear()
        draftValues.value = new Map()
        await refresh()
      } else {
        throw new Error(result.error || '保存失败')
      }
    } catch (e) {
      handleError('保存修改', e)
      throw e
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 获取字段编辑配置
   */
  function getFieldEditConfig(fieldName) {
    const column = columns.value.find(c => c.prop === fieldName || c.name === fieldName)
    return _inferFieldEditConfigSvc(column)
  }
  
  /**
   * 获取单元格显示值（优先草稿值）
   */
  function getCellValue(row, fieldName) {
    const draftRow = draftValues.value.get(row.id)
    if (draftRow && fieldName in draftRow) {
      return draftRow[fieldName]
    }
    // [DECORATIVE] [NEW] v1.2 / FR-3.3: 优先读后端注入的 display_values（如 FK 显示名、枚举标签）
    if (row?.display_values?.[fieldName] !== undefined) {
      return row.display_values[fieldName]
    }
    return row[fieldName]
  }
  
  /**
   * 判断单元格是否正在编辑
   */
  function isEditing(rowId, fieldName) {
    return editingCell.value?.rowId === rowId && editingCell.value?.fieldName === fieldName
  }
  
  /**
   * 判断单元格是否被悬停
   */
  function isHovered(rowId, fieldName) {
    return hoveredCell.value?.rowId === rowId && hoveredCell.value?.fieldName === fieldName
  }
  
  /**
   * 设置悬停单元格
   */
  function setHoveredCell(rowId, fieldName) {
    hoveredCell.value = { rowId, fieldName }
  }
  
  /**
   * 清除悬停状态
   */
  function clearHoveredCell() {
    hoveredCell.value = null
  }

  const navigableAssociations = computed(() => {
    if (!metaConfig.value?.associations) return []
    return metaConfig.value.associations.filter(assoc => {
      const nav = assoc.navigation || {}
      if (nav.enabled === false) return false
      const assocType = assoc.type || ''
      return ['many_to_many', 'composition', 'reverse_many_to_many'].includes(assocType)
    })
  })

  async function getNavigableAssociations() {
    return navigableAssociations.value
  }

  async function batchGetAssociationCounts(associationName) {
    if (selectedIds.value.size === 0) return {}
    const ids = Array.from(selectedIds.value)
    try {
      const result = await boService.batchQueryAssociations(objectType, associationName, {
        source_ids: ids,
        page: 1,
        page_size: 1
      })
      if (result.success && result.data?.counts) {
        return result.data.counts
      }
      return {}
    } catch (e) {
      return {}
    }
  }

  // ======== 自动初始化 ========
  onMounted(() => {
    init()
  })

  onUnmounted(() => {
    selectedIds.value = new Set()
    selectedRows.value = []
    headerFilterValues.value = {}
    filterValues.value = {}
    contextFilters.value = {}
    draftValues.value = new Map()
  })

  // ======== 返回公共接口 =======
  
  return {
    // 元数据和配置
    metaConfig,
    objectType,
    config,
    
    // 列表相关
    columns,
    visibleColumns,
    data,
    loading,
    selectedRows,
    selectedIds,
    isAllPagesSelected,
    // [FR-008 v1] 选区上限
    selectionLimitHit,
    MAX_SELECTION_LIMIT,
    totalSelectedCount,
    currentPageSelectedCount,
    
    // 导入导出对话框状态
    showExportDialog,
    showImportDialog,
    
    // 过滤器相关
    filterFields,
    visibleFilterFields,
    filterValues,
    headerFilterValues,
    contextFilters,
    setContextFilters,
    apiFilterConfigs,
    
    // 搜索相关（单一事实原则：从元数据获取）
    searchFields,
    keyword,
    
    // 导出过滤器参数（与列表查询使用相同的格式）
    exportFilters,
    
    // 操作按钮
    toolbarActions,
    toolbarRightActions,
    rowActions,
    batchActions,
    exportFields,
    importOptions,
    
    // 分页和排序
    pagination,
    paginationConfig,
    sortInfo,
    defaultSort,
    filteredTotalCount,

    // [FIX 2026-06-08] 权限不足标记
    permissionDenied,
    
    // 过滤器显示模式
    filterDisplayModeConfig,
    
    // 行选择配置
    selectionConfig: computed(() => {
      if (config.displayMode === 'dialog') {
        return { enabled: true, mode: 'multiple' }
      }
      if (config.displayMode === 'embedded') {
        const hasBatchOrRowActions = rowActions.value.length > 0 || batchActions.value.length > 0
        const metaSelectable = metaConfig.value?.list?.selectable || metaConfig.value?.list?.selection?.enabled
        return { enabled: hasBatchOrRowActions || !!metaSelectable, mode: 'multiple' }
      }
      const metaSelectable = metaConfig.value?.list?.selectable || metaConfig.value?.list?.selection?.enabled
      return {
        enabled: rowActions.value.length > 0 || batchActions.value.length > 0 || !!metaSelectable,
        mode: metaConfig.value?.list?.selection?.mode || 'multiple'
      }
    }),
    
    // 核心方法
    init,
    loadList,
    refresh,
    handleAction,
    handleToolbarAction,
    handleBatchAction,
    handleFilter,
    handleSearch,
    handleSortChange,
    handlePageChange,
    handlePageSizeChange,
    handleSelectionChange,
    handleHeaderFilter,
    resetHeaderFilter,
    resetFilters,
    getRowActions,
    
    // 批量操作方法
    handleBatchDelete,
    handleBatchExport,
    handleBatchImport,
    
    // 导入导出成功处理
    handleExportSuccess,
    handleImportSuccess,
    
    // 跨页选择方法
    selectAllCurrentPage,
    selectAllPages,
    clearAllSelection,
    
    // Inline Edit 相关
    inlineEditConfig,
    inlineEditMode,
    draftValues,
    editingCell,
    hoveredCell,
    hasUnsavedChanges,
    
    // Inline Edit 方法
    enableInlineEdit,
    disableInlineEdit,
    startEditCell,
    finishEditCell,
    updateDraftValue,
    addNewRow,
    cancelInlineEdit,
    saveDraftValues,
    getDraftCreates,
    isCellEditable,
    getFieldEditConfig,
    getCellValue,
    isEditing,
    isHovered,
    setHoveredCell,
    clearHoveredCell,

    navigableAssociations,
    getNavigableAssociations,
    batchGetAssociationCounts
  }
}

// ======== 辅助函数（可在组件中使用）=====

/**
 * 格式化日期时间
 * @param {*} value - 日期值
 * @param {String} format - 格式化模式
 * @returns {String} 格式化后的字符串
 */
export function formatDate(value, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!value) return '-'
  
  const date = new Date(value)
  if (isNaN(date.getTime())) return '-'

  try {
    return dateFormatService.format(date)
  } catch (e) {
    return '-'
  }
}

/**
 * 截断文本（用于 ellipsis 类型列）
 * @param {String} text - 原始文本
 * @param {Number} maxLength - 最大长度
 * @returns {String} 截断后的文本
 */
export function truncateText(text, maxLength = 20) {
  if (!text) return '-'
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

/**
 * 获取状态标签类型（用于 status/badge 类型的列）
 * @param {*} status - 状态值
 * @param {Object} colorMap - 状态→颜色映射
 * @returns {String} Element Plus tag type
 */
export function getStatusTagType(status, colorMap = {}) {
  const map = {
    active: 'success',
    inactive: 'info',
    locked: 'danger',
    enabled: 'success',
    disabled: 'info',
    ...colorMap
  }
  return map[status] || 'info'
}

export default useMetaList
