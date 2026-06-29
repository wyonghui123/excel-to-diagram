import { defineStore } from 'pinia'
import { ref, computed, shallowRef } from 'vue'

export const useDiagramConfigStore = defineStore('diagramConfig', () => {
  // 图表类型
  // 关键修复 v34: chartType 默认 'businessObject' (业务对象图)
  //   原因: 用户反馈"类型默认选中业务对象图"
  //   之前默认 '', 用户走到 step 3 (类型选择) 才能手动选; 现在自动选
  //   注意: sessionStorage 恢复优先于默认值 (F5 刷新后保留用户上次选择)
  const chartType = ref('businessObject')
  const previousChartType = ref('')
  const chartTypeChanged = ref(false)

  // 配色配置
  const colorScheme = ref('default')
  const colorGroupBy = ref('domain')
  const nodeTextColor = ref('black')
  const centerScopeColor = ref('#808080')
  const centerDomainColor = ref('#D9D9D9')
  const centerScopeHighlight = ref(true)

  // 中心范围配置
  const centerDomain = ref('')
  const centerScope = ref([])
  // [M2 PR-2.1] centerScopeMarkers 包含 3 个 Map，整体替换模式 (updateCenterScopeMarkers 整体赋值)
  //   改 shallowRef 避免对内部 Map 创建 Proxy
  const centerScopeMarkers = shallowRef({
    domains: new Map(),
    subDomains: new Map(),
    serviceModules: new Map()
  })

  // 布局配置
  const layoutTemplate = ref('default')
  const layoutEngine = ref('elk')
  const layoutType = ref('grouped')
  const assignmentMode = ref('auto')

  // 其他配置
  const customColors = ref({})
  // [M2 PR-2.1] positions 节点位置数组可能包含 1000+ 节点坐标，整体替换模式 (updatePositions 整体赋值)
  //   改 shallowRef 避免深度代理开销
  const positions = shallowRef([])
  const preserveModelOrder = ref(false)
  const hideLinkLabelTails = ref(null)
  const annotationPanelPosition = ref('bottom')
  const showAnnotationIcons = ref(false)
  const useUnifiedRenderer = ref(true)

  // 分组控制配置
  const layoutControlConfig = ref({
    enabled: false,
    overallDirection: 'TB',
    groups: [],
    engine: 'elk',
    preserveOrder: true
  })

  // 渲染限制配置
  const mermaidMaxTextSize = ref(500000)

  // Getters
  const centerBoCodes = computed(() => new Set(centerScope.value || []))

  const resolvedColorConfig = computed(() => ({
    colorScheme: colorScheme.value,
    colorGroupBy: colorGroupBy.value,
    nodeTextColor: nodeTextColor.value,
    centerScopeColor: centerScopeColor.value,
    customColors: customColors.value
  }))

  const isBusinessObjectChart = computed(() => chartType.value === 'businessObject')
  const isServiceModuleChart = computed(() => chartType.value === 'serviceModule')

  // Actions
  function updateColorScheme(value) {
    colorScheme.value = value?.value ?? value ?? 'default'
  }

  function updateColorGroupBy(value) {
    colorGroupBy.value = value?.value ?? value ?? 'domain'
  }

  function updateNodeTextColor(value) {
    nodeTextColor.value = value?.value ?? value ?? 'black'
  }

  function updateCenterScopeColor(value) {
    centerScopeColor.value = value?.value ?? value ?? '#808080'
  }

  function updateCenterDomain(value) {
    centerDomain.value = value?.value ?? value ?? ''
  }

  function updateCenterDomainColor(value) {
    centerDomainColor.value = value?.value ?? value ?? '#D9D9D9'
  }

  function updateCenterScopeHighlight(value) {
    centerScopeHighlight.value = value?.value ?? value ?? true
  }

  function updateCenterScope(codes) {
    centerScope.value = Array.isArray(codes) ? codes : (codes?.value || [])
  }

  function updateCenterScopeMarkers(markers) {
    centerScopeMarkers.value = markers || { domains: new Map(), subDomains: new Map(), serviceModules: new Map() }
  }

  function updateChartType(type) {
    const typeValue = typeof type === 'string' ? type : (type?.value || '')
    if (chartType.value && chartType.value !== typeValue) {
      previousChartType.value = chartType.value
      chartTypeChanged.value = true
    } else {
      chartTypeChanged.value = false
    }
    chartType.value = typeValue
    // 关键修复 v33: 持久化 chartType 到 sessionStorage (F5 刷新后能恢复)
    //   原因: chartType='' 时 StepConfig 的颜色配置区域 (CenterDomainSelect / ServiceModuleConfig)
    //   因 v-if 条件不满足不渲染, 用户刷新后整个颜色区域消失
    if (typeValue) {
      sessionStorage.setItem('archDataChartType', typeValue)
    } else {
      sessionStorage.removeItem('archDataChartType')
    }
  }

  function updatePreviousChartType(value) {
    previousChartType.value = value
  }

  function setChartTypeChanged(value) {
    chartTypeChanged.value = value
  }

  function resetChartTypeChanged() {
    chartTypeChanged.value = false
  }

  function updateLayoutTemplate(value) {
    layoutTemplate.value = value?.value ?? value ?? 'default'
  }

  function updateLayoutEngine(value) {
    layoutEngine.value = value?.value ?? value ?? 'elk'
  }

  function updateLayoutType(value) {
    layoutType.value = value?.value ?? value ?? 'grouped'
  }

  function updateCustomColors(colors) {
    customColors.value = colors?.value || colors || {}
  }

  function updatePositions(newPositions) {
    positions.value = newPositions?.value || newPositions || []
  }

  function updateHideLinkLabelTails(value) {
    hideLinkLabelTails.value = value?.value ?? value ?? null
  }

  function updateLayoutControlConfig(config) {
    layoutControlConfig.value = config?.value || config
  }

  function updateMermaidMaxTextSize(value) {
    mermaidMaxTextSize.value = typeof value === 'number' ? value : (parseInt(value) || 500000)
  }

  function updateAnnotationPanelPosition(value) {
    annotationPanelPosition.value = value?.value ?? value ?? 'bottom'
  }

  function updateShowAnnotationIcons(value) {
    showAnnotationIcons.value = value?.value ?? value ?? false
  }

  function updateAssignmentMode(value) {
    assignmentMode.value = value?.value ?? value ?? 'auto'
  }

  function fallbackToLegacyRenderer() {
    useUnifiedRenderer.value = false
  }

  function resetConfig() {
    chartType.value = ''
    sessionStorage.removeItem('archDataChartType')
    previousChartType.value = ''
    chartTypeChanged.value = false
    colorScheme.value = 'default'
    colorGroupBy.value = 'domain'
    nodeTextColor.value = 'black'
    centerScopeColor.value = '#808080'
    centerDomainColor.value = '#D9D9D9'
    centerScopeHighlight.value = true
    centerDomain.value = ''
    centerScope.value = []
    centerScopeMarkers.value = {
      domains: new Map(),
      subDomains: new Map(),
      serviceModules: new Map()
    }
    layoutTemplate.value = 'default'
    layoutEngine.value = 'elk'
    layoutType.value = 'grouped'
    assignmentMode.value = 'auto'
    customColors.value = {}
    positions.value = []
    preserveModelOrder.value = false
    hideLinkLabelTails.value = null
    annotationPanelPosition.value = 'bottom'
    showAnnotationIcons.value = false
    useUnifiedRenderer.value = false
    layoutControlConfig.value = {
      enabled: false,
      overallDirection: 'TB',
      groups: [],
      engine: 'elk',
      preserveOrder: true
    }
    mermaidMaxTextSize.value = 500000
  }

  return {
    // State
    chartType,
    previousChartType,
    chartTypeChanged,
    colorScheme,
    colorGroupBy,
    nodeTextColor,
    centerScopeColor,
    centerDomainColor,
    centerScopeHighlight,
    centerDomain,
    centerScope,
    centerScopeMarkers,
    layoutTemplate,
    layoutEngine,
    layoutType,
    assignmentMode,
    customColors,
    positions,
    preserveModelOrder,
    hideLinkLabelTails,
    annotationPanelPosition,
    showAnnotationIcons,
    useUnifiedRenderer,
    layoutControlConfig,
    mermaidMaxTextSize,

    // Getters
    centerBoCodes,
    resolvedColorConfig,
    isBusinessObjectChart,
    isServiceModuleChart,

    // Actions
    updateColorScheme,
    updateColorGroupBy,
    updateNodeTextColor,
    updateCenterScopeColor,
    updateCenterDomain,
    updateCenterDomainColor,
    updateCenterScopeHighlight,
    updateCenterScope,
    updateCenterScopeMarkers,
    updateChartType,
    updatePreviousChartType,
    setChartTypeChanged,
    resetChartTypeChanged,
    updateLayoutTemplate,
    updateLayoutEngine,
    updateLayoutType,
    updateCustomColors,
    updatePositions,
    updateHideLinkLabelTails,
    updateLayoutControlConfig,
    updateMermaidMaxTextSize,
    updateAnnotationPanelPosition,
    updateShowAnnotationIcons,
    updateAssignmentMode,
    fallbackToLegacyRenderer,
    resetConfig
  }
})
