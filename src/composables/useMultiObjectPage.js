/**
 * useMultiObjectPage — 通用多对象管理页面的核心逻辑
 *
 * ============================================================
 *  元数据驱动架构（Metadata-Driven Architecture）
 * ============================================================
 *
 * 【设计原则】
 *   本 composable 是通用模块，只依赖输入参数 `objectTypes: string[]`，
 *   所有过滤逻辑、层级关系、FK 映射均从元数据自动推导，不包含任何硬编码。
 *
 * 【输入】
 *   - objectTypes: string[]          例如 ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
 *   - config.defaultTab              默认激活 Tab
 *   - config.tabs[type].label        自定义 Tab 标签（可选，否则从 hierarchyTypes.getLabel 取）
 *   - config.customFilterBuilders    非层级、非关系类型的自定义过滤构建器
 *
 * 【元数据来源】
 *   1. hierarchies.yaml (via useHierarchyTypes)
 *      - levels:            product → version → domain → sub_domain → service_module → business_object
 *      - getParentType():   返回父对象类型
 *      - getChildType():    返回子对象类型
 *      - getLevelIndex():   返回层级索引
 *
 *   2. 各对象 YAML (via filterFlow + cross_table_filters)
 *      - globalFilters:     自动检测 ≥2 个对象共有的 cross_table_filter → 全局过滤
 *
 *   3. relationship.yaml
 *      - 关系类型(relation_code)
 *      - 备注类型(category_types)：通过 cross_table_filters 的 annotation_category EXISTS 子查询实现
 *
 * 【过滤映射模型（完全元数据驱动）】
 *
 *   对象树                          Tab 过滤机制
 *   ─────────                      ──────────────
 *   产品(product)
 *   └─ 版本(version)               version_id → versionContext 上下文过滤（全局）
 *      ├─ 领域(domain)      ───→   domain Tab:     id__in = [选中的 domain IDs]
 *      │                           sub_domain Tab: domain_id__in = [选中的 domain IDs]
 *      │                                           ↑ FK: {parentType}_id 自动推导
 *      ├─ 子领域(sub_domain) ──→   sub_domain Tab: id__in = [选中的 sub_domain IDs]
 *      │                           service_module Tab: sub_domain_id__in = [选中的 sub_domain IDs]
 *      ├─ 服务模块(svc_mod)  ──→   service_module Tab: id__in = [选中的 SM IDs]
 *      │                           business_object Tab: service_module_id__in = [选中的 SM IDs]
 *      │                           ↑ 业务对象是服务模块的 composition 关系（getChildren）
 *      └─ 业务对象(bo)       ──→   business_object Tab: id__in = [选中的 BO IDs]
 *
 *   关系(relationship)      ──→   relationship Tab: relation_code__in + category_types__in
 *                                ↑ 关系通过关联类型(relation_code)区分，独立于层级树
 *
 *   【过滤优先级】每个 Tab 的过滤策略（_buildHierarchyFilters）：
 *     1. 直接选区:   typeScope.selected → id__in
 *     2. 有效选区:   typeScope.effective → id__in
 *     3. 父级 FK:    parentType.selected/effective → {parentType}_id__in
 *        （FK 字段名约定：{父对象类型}_id，如 parentType='service_module' → FK='service_module_id'）
 *
 *   【composition 关系】（业务对象 ⇄ 服务模块）
 *     - business_object 是 service_module 的 composition 子对象
 *     - BO Tab 过滤: service_module_id__in → 本质是 getChildren（通过 FK 查询子对象）
 *     - SM Tab 过滤: id__in → SM 本身直接选中
 *     - 对象树不加载 BO 节点（仅加载 domain → sub_domain → service_module），BO 通过 FK 间接体现
 *
 *   全局过滤(globalFilters):
 *     - annotation_category__in → 自动检测：cross_table_filter 出现在 ≥2 个对象 YAML 中
 *     - 仅对非 relationship 且声明了 cross_table_filters 的对象生效
 *
 * 【关联关系机制】（关系 Tab）
 *   - 关系(relationship) 通过 relation_code（关联类型）区分，独立于层级树
 *   - source_bo_id / target_bo_id 关联双方业务对象
 *   - 支持 realtion_code__in / category_types__in / filterRelationCodes 组合过滤
 *
 * 【关键约定】
 *   - FK 命名: {parentObjectType}_id（如 domain_id, service_module_id）
 *   - API 过滤参数: {fk_field}__in（如 domain_id__in）
 *   - 对象树 scope 事件约定: selected{Type}Ids + effective{Type}Ids（如 selectedDomainIds）
 *   - 此约定是元数据驱动的核心，打破了层级、对象类型的硬编码依赖
 *
 * 【使用示例】
 *   const page = useMultiObjectPage(
 *     ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship'],
 *     { defaultTab: 'relationship' }
 *   )
 *   // page.activeTab, page.tabs, page.combinedFilters, page.handleScopeChange, ...
 */
import { ref, computed, watch, reactive, provide } from 'vue'
import { useVersionContext } from './useVersionContext'
import { useFilterFlow } from './useFilterFlow'
import { useContextFilterSource } from './filterSources/useContextFilterSource'
import { useScopeFilterSource } from './filterSources/useScopeFilterSource'
import { useHierarchyTypes } from './useHierarchyTypes'
import * as hierarchyService from '@/services/hierarchyService'

/**
 * 约定：FK 字段命名 = 父对象类型 + '_id'
 *
 * 从 hierarchies.yaml 的 foreign_key_field 可知:
 *   business_object → service_module_id (parent: service_module)
 *   service_module  → sub_domain_id     (parent: sub_domain)
 *   sub_domain      → domain_id         (parent: domain)
 *   domain          → version_id        (parent: version)
 *
 * 因此通用推导: getFKField(type) = getParentType(type) + '_id'
 *
 * @deprecated 使用 hierarchyService.getFKField(levels, type) 替代
 */

/**
 * 判断是否为层级对象类型（product/version 除外，它们在树外由 versionContext 管理）
 * 层级类型 = 从 domain 到 business_object 的所有 hierarchy levels
 *
 * @deprecated 使用 hierarchyService.isHierarchyType(levels, type) 替代
 */

export function useMultiObjectPage(objectTypes, config = {}, coordinator = null) {
  const hierarchyTypes = useHierarchyTypes()
  const metaObjectRef = ref(null)
  provide('metaObject', metaObjectRef)

  // 便捷引用：层级配置数组（供 hierarchyService 纯函数使用）
  const levels = hierarchyTypes.levels

  // ============================================================
  //  Tab 状态
  // ============================================================
  const activeTab = ref(config.defaultTab || objectTypes[0])

  const tabs = computed(() => {
    if (!objectTypes || !objectTypes.length) return []
    return objectTypes
      .filter(Boolean)
      .map(type => ({
        name: type,
        label: config.tabs?.[type]?.label || hierarchyService.getLabel(levels.value, type),
        icon: hierarchyService.getIcon(levels.value, type)
      }))
      .filter(Boolean)
  })

  // ============================================================
  //  版本上下文（全局，控制 version_id 过滤）
  // ============================================================
  const versionContext = useVersionContext({
    autoLoadProducts: true,
    autoRestore: true
  })

  const filterFlow = useFilterFlow({
    aggregator: { strategy: 'merge' },
    autoRefreshDependencies: true,
    refreshMode: 'debounced',
    refreshDebounce: 300
  })

  const contextSource = useContextFilterSource({
    id: 'version-context',
    contextField: 'version_id',
    label: '版本'
  })
  filterFlow.registerSource(contextSource.source)

  const scopeSource = useScopeFilterSource({
    id: 'multi-object-scope',
    label: 'Scope',
    metaObject: metaObjectRef
  })
  filterFlow.registerSource(scopeSource.source)

  watch(
    () => versionContext.selectedVersionId.value,
    (newId) => {
      if (newId) {
        contextSource.setContext(newId)
      }
    },
    { immediate: true }
  )

  // ============================================================
  //  Scope 选区状态（元数据驱动：按输入的 objectTypes 动态生成）
  // ============================================================
  const scopeIds = reactive({})
  objectTypes.forEach(type => {
    scopeIds[type] = { selected: [], effective: [] }
  })
  scopeIds.globalFilters = {}
  scopeIds.relationExtra = { relationCodes: [], relationIds: [], categoryTypes: [], filterRelationCodes: [] }

  const hasScopeSelection = computed(() => {
    return objectTypes.some(type => {
      const ids = scopeIds[type]
      return ids && (ids.selected.length > 0 || ids.effective.length > 0)
    }) || scopeIds.relationExtra.relationCodes.length > 0
  })

  /**
   * 动态过滤键列表（元数据驱动）
   *
   * 用于在构建 combinedFilters 时，先清除 filterFlow 中已存在的 scope 相关过滤键，
   * 再从 scopeIds 重新构建，确保 scope 过滤始终是最新且一致的。
   *
   * 包含：
   *   - id__in（所有层级类型）
   *   - {parentType}_id__in（FK 过滤，从 hierarchyTypes.getParentType 推导）
   *   - relation_*（关系类型过滤）
   *   - annotation_*（全局过滤）
   *   - scopeSource 内部键
   */
  const scopeFilterKeys = computed(() => {
    const keys = new Set()

    keys.add('id__in')
    keys.add('annotation_category__in')
    keys.add('annotation_categories')
    keys.add('relation_code__in')
    keys.add('category_types__in')
    keys.add('category_types')
    keys.add('relation_codes')
    keys.add('filter_relation_codes')
    keys.add('source_bo_ids')
    keys.add('target_bo_ids')

    objectTypes.filter(t => hierarchyService.isHierarchyType(levels.value, t)).forEach(type => {
      const parentType = hierarchyService.getParentType(levels.value, type)
      if (parentType) {
        keys.add(`${parentType}_id__in`)
      }
      const mappings = hierarchyService.getFilterMappings(levels.value, type)
      mappings.forEach(m => {
        if (m.trigger === 'parent' || m.trigger === 'entity_scope') {
          keys.add(`${m.filter_field}__in`)
        }
      })
    })

    const assocMappings = hierarchyService.getFilterMappings(levels.value, 'relationship')
    assocMappings.forEach(m => {
      if (m.trigger === 'entity_scope') {
        keys.add(`${m.filter_field}__in`)
      }
    })

    return [...keys]
  })

  // ============================================================
  //  合并过滤（元数据驱动 + precompute 所有 Tab）
  //
  //  tabFilters: scopeIds 变更时一次性计算所有 objectType 的 per-type 过滤 delta
  //  combinedFilters: 合并 base + global + precomputed per-type delta
  // ============================================================
  // [FIX v3.18] 强制重算计数器 + 显式 watch relationExtra 的每个属性：
  //   Vue 3 的 watch 对 reactive object 的 deep 模式有时不触发（特别是在 cross-module reactive proxy
  //   传递场景下，buildAssociationFilterParams 内部读取的属性未被 computed 追踪到）。
  //   显式 watch 每个属性确保 watch 必触发；computed 显式读取 + Object.assign snapshot
  //   确保重新计算时拿到最新值。
  const tabFiltersVersion = ref(0)
  const tabFilters = computed(() => {
    // 显式读取计数 → 让 computed 依赖此 ref
    void tabFiltersVersion.value
    const result = {}
    objectTypes.forEach(type => {
      result[type] = _computeTypeFilters(type)
    })
    return result
  })

  // 显式 watch relationExtra 的每个属性（避免 deep watch 不触发的问题）
  watch(
    [
      () => scopeIds.relationExtra.relationIds,
      () => scopeIds.relationExtra.relationCodes,
      () => scopeIds.relationExtra.categoryTypes,
      () => scopeIds.relationExtra.filterRelationCodes
    ],
    () => {
      tabFiltersVersion.value++
    }
  )

  function _computeTypeFilters(objectType) {
    const filters = {}

    if (config.customFilterBuilders?.[objectType]) {
      return config.customFilterBuilders[objectType](filters, scopeIds)
    }

    if (hierarchyService.isAssociation(levels.value, objectType)) {
      return _buildAssociationFilters(filters)
    }

    if (hierarchyService.isEntity(levels.value, objectType)) {
      return _buildHierarchyFilters(filters, objectType)
    }

    return _buildRelationshipFilters(filters)
  }

  const combinedFilters = computed(() => {
    const baseFilters = filterFlow.combinedFilters.value
    const filters = { ...baseFilters }

    scopeFilterKeys.value.forEach(k => delete filters[k])

    const globalFilters = scopeIds.globalFilters
    Object.keys(globalFilters).forEach(key => {
      const val = globalFilters[key]
      if (Array.isArray(val) && val.length > 0) {
        filters[`${key}__in`] = val.join(',')
      }
    })

    const currentType = activeTab.value
    if (!currentType) return filters

    const typeDelta = { ...(tabFilters.value[currentType] || {}) }
    if (hierarchyService.isEntity(levels.value, currentType)) {
      const scope = scopeIds[currentType]
      if (scope && (scope.selected.length > 0 || scope.effective.length > 0)) {
        const parentType = hierarchyService.getParentType(levels.value, currentType)
        if (parentType) {
          delete typeDelta[`${parentType}_id__in`]
        }
      }
    }

    const final = { ...filters, ...typeDelta }
    return final
  })

  /**
   * 构建层级过滤（完全元数据驱动）
   *
   * 过滤优先级:
   *  1. typeScope.selected → id__in          （直接选中）
   *  2. typeScope.effective → id__in         （树计算的有效范围）
   *  3. parentScope → {parentType}_id__in    （父级 FK 回退，composition/getChildren）
   *
   * FK 字段从 hierarchyTypes.getParentType() 推导:
   *   目标类型 → 父类型 → FK={父类型}_id
   *   例: business_object → service_module → FK=service_module_id
   *
   * @param {object} filters     - 当前过滤对象（已包含 version_id 等基础过滤）
   * @param {string} objectType  - 当前 Tab 的对象类型
   * @returns {object} 更新后的过滤对象
   */
  function _buildHierarchyFilters(filters, objectType) {
    const result = hierarchyService.buildHierarchyFilterParams({
      levels: levels.value,
      scopeIds,
      objectType
    })
    return { ...filters, ...result }
  }

  /**
   * 构建关系过滤（回退逻辑，当 hierarchyTypes 不提供 filter_mappings 时使用）
   */
  function _buildRelationshipFilters(filters) {
    const result = hierarchyService.buildRelationshipFilterParams(scopeIds.relationExtra)
    return { ...filters, ...result }
  }

  /**
   * 构建关联过滤（association object 专用，完全元数据驱动）
   *
   * 与层级过滤不同，association 对象的 scope 不来自层级 parent，而来自:
   *   - source_bo_id / target_bo_id：从 entity scope 派生（trigger=entity_scope）
   *   - relation_code：关联类型（trigger=selected/effective）
   *   - category_types：虚拟分类（trigger=selected/effective）
   *
   * filter_mappings 中 trigger 含:
   *   - selected/effective: 关系树直接勾选
   *   - entity_scope:      从 source/target entity 的 scopeIds 派生
   *
   * 当 hierarchyTypes 未提供 filter_mappings 时，回退到 _buildRelationshipFilters 逻辑
   *
   * [FIX v3.18] 显式读取 relationExtra 嵌套属性：
   *   当 buildAssociationFilterParams 是非 reactive 纯函数（hierarchyService.js 模块）时，
   *   跨模块边界的 reactive proxy 深度追踪会丢失（Vue 3 已知行为）。
   *   显式在 computed 上下文中读取属性，让 Vue 把这些属性加入 computed 依赖集合，
   *   watch + computed 才能正确响应 Object.assign(scopeIds.relationExtra, {...}) 的变更。
   */
  function _buildAssociationFilters(filters) {
    // 显式读取（触发 Vue 3 响应式追踪）
    const re = scopeIds.relationExtra
    const relationExtraSnapshot = {
      relationIds: re.relationIds,
      relationCodes: re.relationCodes,
      categoryTypes: re.categoryTypes,
      filterRelationCodes: re.filterRelationCodes
    }
    const result = hierarchyService.buildAssociationFilterParams({
      levels: levels.value,
      scopeIds,
      relationExtra: relationExtraSnapshot
    })
    return { ...filters, ...result }
  }

  // ============================================================
  //  Scope 变更处理
  // ============================================================
  /**
   * 处理对象树范围变更
   *
   * 输入: RelationScopeTree emit 的 scope 对象，包含:
   *   boIds, relationCodes, categoryTypes,
   *   selectedDomainIds, effectiveDomainIds,
   *   selectedSubDomainIds, effectiveSubDomainIds,
   *   selectedServiceModuleIds, effectiveServiceModuleIds,
   *   annotationCategories, filterRelationCodes
   *
   * 映射到 scopeIds（按 objectTypes 动态生成键）:
   *   层级类型: scope[`selected{Type}Ids`], scope[`effective{Type}Ids`]
   *   业务对象: scope.boIds（补充逻辑，因 BO 的 selectedKey 为 selectedBusinessObjectIds）
   *   全局过滤: scope.annotationCategories → scopeIds.globalFilters.annotation_category
   *   关系过滤: scope.relationCodes/categoryTypes/filterRelationCodes → scopeIds.relationExtra
   */
  function handleScopeChange(scope) {
    objectTypes.forEach(type => {
      if (hierarchyService.isHierarchyType(levels.value, type)) {
        const selectedKey = `selected${_pascalCase(type)}Ids`
        const effectiveKey = `effective${_pascalCase(type)}Ids`
        scopeIds[type].selected = scope[selectedKey] || []
        scopeIds[type].effective = scope[effectiveKey] || []
      }
    })

    const lastHierarchyType = objectTypes.filter(t => hierarchyService.isHierarchyType(levels.value, t) && !hierarchyService.isAssociation(levels.value, t)).pop()
    if (lastHierarchyType && scopeIds[lastHierarchyType]) {
      scopeIds[lastHierarchyType].selected =
        scopeIds[lastHierarchyType].selected.length > 0
          ? scopeIds[lastHierarchyType].selected
          : (scope.boIds || [])
    }

    scopeIds.globalFilters = {}
    if (scope.annotationCategories && scope.annotationCategories.length > 0) {
      scopeIds.globalFilters.annotation_category = scope.annotationCategories
    }

    // OSS handleBoCheck 不 emit relationCodes，RSS handleClassifierCheck 才 emit
    // relationCodes 为 null/undefined/空数组 → 设置为 [] → watch 触发
    const newRelationCodes = scope.relationCodes == null || scope.relationCodes.length === 0 ? [] : scope.relationCodes
    /**
     * [WARNING] 必须 mutate relationExtra 嵌套属性（而非替换整个对象引用）以触发 Vue 响应式
     * 错误写法：scopeIds.relationExtra = { ... }  // 替换引用会导致下游 computed (tabFilters)
     *                                              // 缓存旧值，因为下游的 buildAssociationFilterParams
     *                                              // 接收的 relationExtra 是旧对象引用，读取的是旧 relationIds。
     * 正确写法：Object.assign 触发深响应式
     */
    Object.assign(scopeIds.relationExtra, {
      relationCodes: newRelationCodes,
      relationIds: scope.relationIds || [],
      categoryTypes: scope.categoryTypes || [],
      filterRelationCodes: scope.filterRelationCodes || []
    })

    scopeSource.setBusinessObjectIds(scope.boIds || [])
    scopeSource.setRelationCodes(scope.relationCodes || [])
    scopeSource.setRelationIds(scope.relationIds || [])
  }

  function clearScope() {
    objectTypes.forEach(type => {
      if (scopeIds[type]) {
        scopeIds[type].selected = []
        scopeIds[type].effective = []
      }
    })
    scopeIds.globalFilters = {}
    scopeIds.relationExtra = { relationCodes: [], relationIds: [], categoryTypes: [], filterRelationCodes: [] }
    scopeSource.clear()
  }

  function handleToolbarChange({ versionId }) {
    if (versionId) {
      const version = versionContext.versions.value.find(v => v.id === versionId)
      if (version) {
        versionContext.selectVersion(version)
      }
    } else {
      versionContext.selectVersion(null)
    }
    clearScope()
    activeTab.value = config.defaultTab || objectTypes[0]
  }

  // ============================================================
  //  Action 状态管理（导入 / 导出 / 图表 / 刷新）
  // ============================================================
  const importDialogVisible = ref(false)
  const exportDialogVisible = ref(false)
  const exportResult = ref(null)
  const refreshTrigger = ref(0)

  const actionsConfig = computed(() => ({
    import: { enabled: true, ...config.actions?.import },
    export: { enabled: true, ...config.actions?.export },
    chart: { enabled: true, require_filters: true, ...config.actions?.chart },
    refresh: { enabled: true, ...config.actions?.refresh }
  }))

  const canImport = computed(() =>
    actionsConfig.value.import.enabled !== false && !!versionContext.selectedVersionId.value
  )
  const canExport = computed(() =>
    actionsConfig.value.export.enabled !== false && !!versionContext.selectedVersionId.value
  )
  const canShowChart = computed(() => {
    if (actionsConfig.value.chart.enabled === false) return false
    if (!versionContext.selectedVersionId.value) return false
    if (actionsConfig.value.chart.require_filters === false) return true
    return hasScopeSelection.value
  })
  const canRefresh = computed(() =>
    actionsConfig.value.refresh.enabled !== false && !!versionContext.selectedVersionId.value
  )

  const importContext = computed(() => ({
    version_id: versionContext.selectedVersionId.value,
    product_id: versionContext.selectedProductId.value
  }))

  const baseFilters = computed(() => {
    const f = {}
    if (versionContext.selectedVersionId.value) f.version_id = versionContext.selectedVersionId.value
    if (versionContext.selectedProductId.value) f.product_id = versionContext.selectedProductId.value
    return f
  })

  const exportFilters = computed(() => {
    const f = { ...baseFilters.value }

    for (const type of objectTypes) {
      if (!hierarchyService.isHierarchyType(levels.value, type)) continue
      const scope = scopeIds[type]
      if (!scope) continue
      const ids = scope.selected.length > 0
        ? [...scope.selected]
        : scope.effective.length > 0
          ? [...scope.effective]
          : []
      if (ids.length > 0) {
        f[`${type}_id`] = ids
      }
    }

    Object.keys(scopeIds.globalFilters).forEach(key => {
      const val = scopeIds.globalFilters[key]
      if (Array.isArray(val) && val.length > 0) {
        f[key] = val
      }
    })

    const extra = scopeIds.relationExtra
    // [FIX] 优先使用 relationIds（精确 ID 过滤）：当 relationIds 已设置时，跳过 relation_codes
    // 避免后端 AND 语义（id__in AND relation_code__in）把 relation_code 为空的跨域记录（id=29）错误排除。
    // relationIds 已是精确的 ID 列表（包含 INTERNAL + CROSS_BOUNDARY），无需再用 code 二次过滤。
    const hasRelationIds = (extra.relationIds?.length || 0) > 0
    if (!hasRelationIds) {
      let relationCodes = [...(extra.relationCodes || [])]
      if (extra.filterRelationCodes?.length > 0) {
        if (relationCodes.length > 0) {
          relationCodes = relationCodes.filter(r => extra.filterRelationCodes.includes(r))
        } else {
          relationCodes = [...extra.filterRelationCodes]
        }
      }
      if (relationCodes.length > 0) {
        f.relation_codes = relationCodes
      }
    }
    if (extra.categoryTypes?.length > 0) {
      f.category_types = [...extra.categoryTypes]
    }

    return f
  })

  const exportContext = computed(() => ({
    objectType: activeTab.value,
    filters: combinedFilters.value,
    objectTypes: objectTypes.filter(t => t !== 'relationship')
  }))

  const objectTypeLabels = computed(() => {
    const labels = {}
    for (const type of objectTypes) {
      if (type === 'relationship') {
        labels[type] = hierarchyService.getLabel(levels.value, type) || '关系'
      } else {
        labels[type] = hierarchyService.getLabel(levels.value, type) || type
      }
    }
    return labels
  })

  function handleGlobalAction(action) {
    switch (action) {
      case 'import':
        importDialogVisible.value = true
        break
      case 'export':
        exportDialogVisible.value = true
        break
      case 'chart':
        return handleShowChart()
      case 'refresh':
        if (coordinator) {
          coordinator.refreshAll()
        } else {
          refreshTrigger.value++
        }
        break
    }
  }

  function handleShowChart() {
    // 在跳转图表前快照当前状态, 以便返回时恢复
    saveStateForDiagram()

    // 映射层级类型 -> chart app fetchPreviewData 期望的 hierarchyFilter 字段名
    // fetchPreviewData 期望键: domain_id / sub_domain_id / service_module_id / business_object_id (数组)
    const typeToFieldMap = {
      domain: 'domain_id',
      sub_domain: 'sub_domain_id',
      service_module: 'service_module_id',
      business_object: 'business_object_id'
    }

    // 基于 scopeIds 重新构建 hierarchyFilter（不再直接透传 combinedFilters，
    // 因为 combinedFilters 的键是 `${parentType}_id__in`（逗号拼接字符串），
    // 与 chart app 期望的 `*_id`（数组）格式不一致）
    const hierarchyFilter = {}
    objectTypes.forEach(type => {
      const fieldName = typeToFieldMap[type]
      if (!fieldName) return

      const scope = scopeIds[type]
      if (!scope) return

      // 优先使用 selected（用户在树上直接勾选），其次 effective（树计算的可见范围）
      const ids = scope.selected.length > 0
        ? [...scope.selected]
        : scope.effective.length > 0
          ? [...scope.effective]
          : []

      if (ids.length > 0) {
        hierarchyFilter[fieldName] = ids
      }
    })

    const chartData = {
      versionId: versionContext.selectedVersionId.value,
      productId: versionContext.selectedProductId.value,
      hierarchyFilter
    }

    // 保留 selectedXxxIds 字段以兼容 chart app 可能的直接读取
    objectTypes.forEach(type => {
      if (scopeIds[type] && scopeIds[type].selected.length > 0) {
        chartData[`selected${_pascalCase(type)}Ids`] = [...scopeIds[type].selected]
      }
    })

    // 关系类型过滤：chart app 的 initFromArchDataManager 期望字段名 relationTypeFilter
    const relationExtra = scopeIds.relationExtra || {}
    const relationCodesForChart = relationExtra.relationCodes?.length > 0
      ? [...relationExtra.relationCodes]
      : relationExtra.filterRelationCodes?.length > 0
        ? [...relationExtra.filterRelationCodes]
        : []

    if (relationCodesForChart.length > 0) {
      chartData.relationTypeFilter = relationCodesForChart
    }

    return chartData
  }

  // 架构管理 → 图表展示 → 返回 状态持久化
  // 跳转前快照到 sessionStorage, 返回时由调用方读取并恢复 (避免 SPA 卸载导致 in-memory state 全部丢失)
  const STATE_RESTORE_KEY = 'archManagerStateBeforeDiagram'

  function saveStateForDiagram() {
    try {
      const state = {
        activeTab: activeTab.value,
        scopeIds: {},
        tabFilters: JSON.parse(JSON.stringify(tabFilters.value || {})),
        initialBoIds: [],
        initialRelationCodes: [],
        savedAt: Date.now()
      }

      Object.keys(scopeIds).forEach(key => {
        if (key === 'globalFilters') return
        if (key === 'relationExtra') {
          state.scopeIds[key] = JSON.parse(JSON.stringify(scopeIds[key] || {}))
          return
        }
        const scope = scopeIds[key]
        if (scope) {
          state.scopeIds[key] = {
            selected: [...(scope.selected || [])],
            effective: [...(scope.effective || [])]
          }
        }
      })

      // 树的初始勾选 (驱动 ObjectScopeSection / RelationScopeSection 第一次挂载)
      const boScope = scopeIds.business_object
      if (boScope?.selected?.length) {
        state.initialBoIds = [...boScope.selected]
      }
      const relExtra = scopeIds.relationExtra
      if (relExtra?.relationCodes?.length) {
        state.initialRelationCodes = [...relExtra.relationCodes]
      }

      sessionStorage.setItem(STATE_RESTORE_KEY, JSON.stringify(state))
    } catch (e) {
      console.warn('[useMultiObjectPage] Failed to save state for diagram:', e)
    }
  }

  function restoreStateFromDiagram() {
    try {
      if (sessionStorage.getItem('returningFromDiagram') !== 'true') return false
      const stored = sessionStorage.getItem(STATE_RESTORE_KEY)
      // 无论是否成功解析, 都要清掉 flag 防止后续误触发
      sessionStorage.removeItem('returningFromDiagram')
      if (!stored) return false

      const state = JSON.parse(stored)
      if (!state || typeof state !== 'object') return false

      if (state.activeTab && tabs.value.find(t => t.name === state.activeTab)) {
        activeTab.value = state.activeTab
      }

      if (state.scopeIds) {
        Object.keys(state.scopeIds).forEach(key => {
          if (key === 'relationExtra') {
            if (scopeIds.relationExtra) {
              Object.assign(scopeIds.relationExtra, state.scopeIds[key] || {})
            }
            return
          }
          if (scopeIds[key]) {
            scopeIds[key].selected = [...(state.scopeIds[key].selected || [])]
            scopeIds[key].effective = [...(state.scopeIds[key].effective || [])]
          }
        })
      }

      if (state.tabFilters && typeof state.tabFilters === 'object') {
        tabFilters.value = { ...tabFilters.value, ...state.tabFilters }
      }

      // 返回 initialBoIds / initialRelationCodes 供调用方驱动树的重新挂载
      const restored = {
        initialBoIds: [...(state.initialBoIds || [])],
        initialRelationCodes: [...(state.initialRelationCodes || [])]
      }

      sessionStorage.removeItem(STATE_RESTORE_KEY)
      return restored
    } catch (e) {
      console.warn('[useMultiObjectPage] Failed to restore state from diagram:', e)
      return false
    }
  }

  function handleImportSuccess() {
    importDialogVisible.value = false
    if (coordinator) {
      coordinator.refreshAll()
    } else {
      refreshTrigger.value++
    }
  }

  function handleExportSuccess() {
    exportDialogVisible.value = false
  }

  // [E2E] dev 环境暴露给 e2e 测试
  if (typeof window !== 'undefined' && import.meta.env?.DEV) {
    window.__archPage = { objectTypes, activeTab, tabs, versionContext, filterFlow, contextSource, scopeSource, scopeIds, hasScopeSelection, combinedFilters, tabFilters, scopeFilterKeys, handleScopeChange, clearScope, handleToolbarChange }
  }

  return {
    objectTypes,
    activeTab,
    tabs,
    versionContext,
    filterFlow,
    contextSource,
    scopeSource,
    scopeIds,
    hasScopeSelection,
    combinedFilters,
    tabFilters,
    scopeFilterKeys,
    metaObjectRef,
    handleScopeChange,
    clearScope,
    handleToolbarChange,
    importDialogVisible,
    exportDialogVisible,
    exportResult,
    refreshTrigger,
    canImport,
    canExport,
    canShowChart,
    canRefresh,
    handleGlobalAction,
    handleShowChart,
    restoreStateFromDiagram,
    handleImportSuccess,
    handleExportSuccess,
    importContext,
    exportContext,
    objectTypeLabels,
    baseFilters,
    exportFilters
  }
}

function _pascalCase(str) {
  return str
    .split('_')
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')
}