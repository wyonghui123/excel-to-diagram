import { ref, computed } from 'vue'
import { useExcelParser } from '../../../composables/useExcelParser.js'
import { extractSubDomains } from '../../../services/dataTransformer.js'
import { buildDiagramData } from '../../../services/diagramDataBuilder.js'
import { buildServiceModuleDiagramData } from '../../../services/serviceModuleDiagramBuilder.js'

/**
 * 计算服务模块关系（从业务对象关系推导）
 * 与 DataPreview 组件使用相同的逻辑
 */
function computedServiceModuleRelations(relationships, businessObjects, serviceModules) {
  if (!relationships || !businessObjects) {
    return []
  }

  // 创建业务对象编码到服务模块的映射
  const boToModuleMap = new Map()
  businessObjects.forEach(bo => {
    if (bo.code) {
      boToModuleMap.set(bo.code, {
        moduleCode: bo.serviceModule,
        moduleName: bo.serviceModuleName || bo.serviceModule
      })
    }
  })

  // 创建服务模块编码到名称的映射
  const moduleCodeToNameMap = new Map()
  serviceModules?.forEach(sm => {
    if (sm.code) {
      moduleCodeToNameMap.set(sm.code, sm.name)
    }
  })

  // 按服务模块关系分组
  const moduleRelationMap = new Map()

  relationships.forEach(rel => {
    if (!rel.sourceCode || !rel.targetCode) return

    // 获取源和目标业务对象所属的服务模块
    const sourceModule = boToModuleMap.get(rel.sourceCode)
    const targetModule = boToModuleMap.get(rel.targetCode)

    if (!sourceModule?.moduleCode || !targetModule?.moduleCode) return
    if (sourceModule.moduleCode === targetModule.moduleCode) return // 跳过同一服务模块内的关系

    // 服务模块关系编码
    const moduleRelationCode = `${sourceModule.moduleCode}-${targetModule.moduleCode}`

    if (!moduleRelationMap.has(moduleRelationCode)) {
      moduleRelationMap.set(moduleRelationCode, {
        sourceServiceModuleCode: sourceModule.moduleCode,
        sourceServiceModuleName: moduleCodeToNameMap.get(sourceModule.moduleCode) || sourceModule.moduleCode,
        targetServiceModuleCode: targetModule.moduleCode,
        targetServiceModuleName: moduleCodeToNameMap.get(targetModule.moduleCode) || targetModule.moduleCode,
        serviceRelationshipCode: moduleRelationCode,
        businessObjectRelationshipCodes: []
      })
    }

    // 添加业务对象关系编码
    const relation = moduleRelationMap.get(moduleRelationCode)
    if (rel.relationCode && !relation.businessObjectRelationshipCodes.includes(rel.relationCode)) {
      relation.businessObjectRelationshipCodes.push(rel.relationCode)
    }
  })

  return Array.from(moduleRelationMap.values())
}

export function useDiagramData() {
  const { loading, error, previewData, rawData, handleFileUpload, clearData } = useExcelParser()

  const selectedScope = ref([])
  const chartType = ref('') // 'businessObject' 或 'serviceModule'
  const diagramConfig = ref({
    centerDomain: '',
    colorGroupBy: 'domain',
    centerDomainColor: '#D9D9D9',
    colorScheme: 'default',
    textColor: 'black',
    serviceModuleTextColor: 'black',
    layoutTemplate: 'default',
    annotationPanelPosition: 'bottom',
    showAnnotationIcons: false,
    layoutEngine: 'dagre',
    layoutType: 'grouped',
    assignmentMode: 'auto',
    positions: [],
    layoutControlConfig: {
      enabled: false,
      overallDirection: 'TB',
      groups: [],
      engine: 'dagre',
      preserveOrder: true
    }
  })
  const diagramData = ref(null)
  const selectedStats = ref({
    domains: 0,
    subDomains: 0,
    serviceModules: 0,
    businessObjects: 0
  })

  const availableSubDomains = computed(() => {
    return extractSubDomains(previewData.value?.domainProducts)
  })

  const availableDomains = computed(() => {
    if (!previewData.value?.domainProducts) return []
    return previewData.value.domainProducts.map(domain => domain.name)
  })

  const stats = computed(() => {
    if (!previewData.value) {
      return {
        domains: 0,
        subDomains: 0,
        serviceModules: 0,
        businessObjects: 0
      }
    }

    const domains = previewData.value.domainProducts?.length || 0
    let subDomains = 0
    let serviceModules = 0
    let businessObjects = 0

    previewData.value.domainProducts?.forEach(domain => {
      domain.modules?.forEach(subDomain => {
        subDomains++
        subDomain.submodules?.forEach(module => {
          serviceModules++
          businessObjects += module.businessObjects?.length || 0
        })
      })
    })

    return { domains, subDomains, serviceModules, businessObjects }
  })

  const displayStats = computed(() => [
    { key: 'domains', label: '领域', current: selectedStats.value.domains, total: stats.value.domains },
    { key: 'subDomains', label: '子领域', current: selectedStats.value.subDomains, total: stats.value.subDomains },
    { key: 'serviceModules', label: '服务模块', current: selectedStats.value.serviceModules, total: stats.value.serviceModules },
    { key: 'businessObjects', label: '业务对象', current: selectedStats.value.businessObjects, total: stats.value.businessObjects }
  ])

  const generateDiagram = () => {
    console.log('=== generateDiagram 被调用 ===')
    console.log('chartType:', chartType.value)
    console.log('previewData:', previewData.value)

    if (!previewData.value) {
      console.warn('previewData 为空，无法生成图表')
      return
    }

    if (chartType.value === 'serviceModule') {
      console.log('生成服务模块图')
      console.log('服务模块数量:', previewData.value.serviceModules?.length)

      // 从业务对象关系计算服务模块关系（与 DataPreview 组件使用相同的逻辑）
      const serviceModuleRelationships = computedServiceModuleRelations(
        previewData.value.relationships,
        previewData.value.businessObjects,
        previewData.value.serviceModules
      )
      console.log('计算的服务模块关系数量:', serviceModuleRelationships?.length)
      console.log('计算的服务模块关系数据:', serviceModuleRelationships)

      // 服务模块图
      diagramData.value = buildServiceModuleDiagramData({
        serviceModules: previewData.value.serviceModules,
        serviceModuleRelationships: serviceModuleRelationships,
        domainProducts: previewData.value.domainProducts,
        centerSubDomain: diagramConfig.value.centerDomain,
        centerSubDomainColor: diagramConfig.value.centerDomainColor,
        colorGroupBy: diagramConfig.value.colorGroupBy,
        colorScheme: diagramConfig.value.colorScheme,
        serviceModuleTextColor: diagramConfig.value.serviceModuleTextColor,
        layoutTemplate: diagramConfig.value.layoutTemplate
      })
      console.log('服务模块图数据生成完成:', diagramData.value)
      console.log('生成的节点:', diagramData.value.nodes)
      console.log('生成的连线:', diagramData.value.links)
    } else {
      console.log('生成业务对象图')

      // 业务对象图
      diagramData.value = buildDiagramData({
        businessObjects: previewData.value.businessObjects,
        relationships: previewData.value.relationships,
        domainProducts: previewData.value.domainProducts,
        serviceModules: previewData.value.serviceModules,
        centerDomain: diagramConfig.value.centerDomain,
        colorGroupBy: diagramConfig.value.colorGroupBy,
        centerDomainColor: diagramConfig.value.centerDomainColor,
        colorScheme: diagramConfig.value.colorScheme,
        textColor: diagramConfig.value.textColor,
        layoutTemplate: diagramConfig.value.layoutTemplate
      })
      console.log('业务对象图数据生成完成')
    }
  }

  const updateSelectedStats = (newStats) => {
    selectedStats.value = { ...selectedStats.value, ...newStats }
  }

  const resetData = () => {
    clearData()
    selectedScope.value = []
    diagramData.value = null
    selectedStats.value = {
      domains: 0,
      subDomains: 0,
      serviceModules: 0,
      businessObjects: 0
    }
  }

  return {
    // 状态
    loading,
    error,
    previewData,
    rawData,
    selectedScope,
    chartType,
    diagramConfig,
    diagramData,
    selectedStats,

    // 计算属性
    availableSubDomains,
    availableDomains,
    stats,
    displayStats,

    // 方法
    handleFileUpload,
    generateDiagram,
    updateSelectedStats,
    resetData
  }
}
