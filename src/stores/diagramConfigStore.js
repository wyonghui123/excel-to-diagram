import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useDiagramConfigStore = defineStore('diagramConfig', () => {
  // 图表类型
  const chartType = ref('')
  const previousChartType = ref('')
  const chartTypeChanged = ref(false)

  // 配色配置
  const colorScheme = ref('default')
  const colorGroupBy = ref('domain')
  const nodeTextColor = ref('black')
  const centerScopeColor = ref('#EDEDED')
  const centerDomainColor = ref('#D9D9D9')
  const centerScopeHighlight = ref(true)

  // 中心范围配置
  const centerDomain = ref('')
  const centerScope = ref([])
  const centerScopeMarkers = ref({
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
  const positions = ref([])
  const preserveModelOrder = ref(false)
  const hideLinkLabelTails = ref(null)
  const annotationPanelPosition = ref('bottom')
  const showAnnotationIcons = ref(false)
  const useUnifiedRenderer = ref(true)

  // 分组控制配置
  const layoutControlConfig = ref({
    enabled: false,
    overallDirection: 'LR',
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
    centerScopeColor.value = value?.value ?? value ?? '#EDEDED'
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
    previousChartType.value = ''
    chartTypeChanged.value = false
    colorScheme.value = 'default'
    colorGroupBy.value = 'domain'
    nodeTextColor.value = 'black'
    centerScopeColor.value = '#EDEDED'
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
      overallDirection: 'LR',
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
