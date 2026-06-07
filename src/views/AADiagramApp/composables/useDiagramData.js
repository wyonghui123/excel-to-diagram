import { ref, computed, watch, watchEffect, nextTick } from 'vue'
import { useExcelParser } from '../../../composables/useExcelParser.js'
import { useDiagramConfigStore } from '../../../stores/diagramConfigStore.js'
import { extractSubDomains } from '../../../services/dataTransformer.js'
import { buildDiagramData } from '../../../services/diagramDataBuilder.js'
import { buildServiceModuleDiagramData } from '../../../services/serviceModuleDiagramBuilder.js'
import {
  buildGroupModelFromArchitecture,
  buildNodeIdMap,
  filterGroupModelByScope,
  extractTerminalGroups,
  isTerminalGroup,
  ChartType,
  GroupModel,
  mergeUserLayoutConfig,
  enrichGroupModel,
  ColorCalculator,
  UnifiedRenderer
} from '../../../services/groupModel/index.js'
import { DataFlowLogger } from '../../../services/groupModel/dataFlowLogger.js'
import {
  buildRelationCategoryTree,
  getSelectedRelationCodes
} from '../../../services/relationClassifier.js'
import { validateData } from '../../../services/dataValidator.js'
import { buildPreviewDataFromArchData, convertToRelationNodeIds } from '../../../services/archDataConverter.js'

/**
 * @deprecated 旧版非分组控制逻辑，仅在用户启用"启用旧版非分组控制"时使用
 * 此函数将在未来版本移除
 */
function buildLegacyLayoutControlConfig(filteredDomainProducts, filteredContainers, userConfig) {
  console.warn('[useDiagramData] 使用旧版非分组控制逻辑，此模式将在未来版本移除')

  let layoutControlConfig
  const condition1 = !!userConfig
  const condition2 = userConfig?.enabled === true
  const condition3 = !!(userConfig?.groups)
  const condition4 = (userConfig?.groups?.length ?? 0) > 0

  if (condition1 && condition2 && condition3 && condition4) {
    layoutControlConfig = { ...userConfig }
  } else {
    const groups = buildDomainGroups(filteredDomainProducts, filteredContainers)
    layoutControlConfig = {
      enabled: groups.length > 0,
      overallDirection: 'LR',
      groups: groups,
      engine: 'dagre',
      preserveOrder: true
    }
  }

  return layoutControlConfig
}

function buildDomainGroups(domainProducts, containers) {
  if (!domainProducts || domainProducts.length === 0) {
    return []
  }

  const containerArray = Array.isArray(containers) ? containers : []
  const groups = []

  domainProducts.forEach(domain => {
    if (!domain.modules) return

    const childContainers = []

    domain.modules.forEach(module => {
      const container = containerArray.find(c => c.id === module.code || c.name === module.name)
      if (container) {
        childContainers.push({
          id: container.id,
          name: container.name,
          fullTitle: container.fullTitle,
          direction: 'TB'
        })
      }
    })

    if (childContainers.length > 0) {
      groups.push({
        id: domain.name,
        title: domain.name,
        direction: 'LR',
        containers: childContainers
      })
    }
  })

  return groups
}

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
        businessObjectRelationshipCodes: [],
        businessObjectRelationships: []
      })
    }

    // 添加业务对象关系编码（使用源和目标业务对象编码生成）
    const relation = moduleRelationMap.get(moduleRelationCode)
    const boRelCode = `${rel.sourceCode}-${rel.targetCode}`
    if (boRelCode && !relation.businessObjectRelationshipCodes.includes(boRelCode)) {
      relation.businessObjectRelationshipCodes.push(boRelCode)
    }
    
    // 收集业务对象关系的备注
    if (rel.annotationContent) {
      relation.businessObjectRelationships.push({
        relationCode: boRelCode,
        annotationContent: rel.annotationContent,
        annotationCategory: rel.annotationCategory || 'info'
      })
    }
  })

  // 处理备注内容
  const result = []
  moduleRelationMap.forEach((rel) => {
    // 去重后的业务对象关系编码
    const uniqueBoCodes = [...new Set(rel.businessObjectRelationshipCodes.filter(Boolean))]
    
    // 构建备注内容：关系备注内容 + 业务对象关系编码
    const boAnnotations = rel.businessObjectRelationships
      .filter(boRel => boRel.annotationContent)
      .map(boRel => {
        const code = boRel.relationCode || ''
        return code ? `${boRel.annotationContent} ${code}` : boRel.annotationContent
      })
    
    // 去重并用分号连接
    const uniqueAnnotations = [...new Set(boAnnotations)]
    
    result.push({
      sourceServiceModuleCode: rel.sourceServiceModuleCode,
      sourceServiceModuleName: rel.sourceServiceModuleName,
      targetServiceModuleCode: rel.targetServiceModuleCode,
      targetServiceModuleName: rel.targetServiceModuleName,
      serviceRelationshipCode: `${rel.sourceServiceModuleCode}-${rel.targetServiceModuleCode}`,
      businessObjectRelationshipCodes: uniqueBoCodes,
      annotationContent: uniqueAnnotations.join('; ') || '',
      annotationCategory: rel.businessObjectRelationships[0]?.annotationCategory || 'info'
    })
  })

  return result
}

export function useDiagramData() {
  const { loading, error, previewData, rawData, handleFileUpload, clearData } = useExcelParser()
  const configStore = useDiagramConfigStore()
  window.__configStore = configStore

  const centerScope = computed(() => configStore.centerScope)
  const selectedScope = ref([])
  const relationFilteredBoCodes = ref(null)
  const internalRelationFilter = ref('off')
  const chartType = computed(() => configStore.chartType)
  const previousChartType = computed(() => configStore.previousChartType)
  const chartTypeChanged = computed(() => configStore.chartTypeChanged)

  const diagramConfig = computed(() => ({
    chartType: configStore.chartType,
    previousChartType: configStore.previousChartType,
    chartTypeChanged: configStore.chartTypeChanged,
    colorScheme: configStore.colorScheme,
    colorGroupBy: configStore.colorGroupBy,
    nodeTextColor: configStore.nodeTextColor,
    centerScopeColor: configStore.centerScopeColor,
    centerDomain: configStore.centerDomain,
    centerDomainColor: configStore.centerDomainColor,
    centerScopeHighlight: configStore.centerScopeHighlight,
    centerScope: configStore.centerScope,
    centerScopeMarkers: configStore.centerScopeMarkers,
    layoutTemplate: configStore.layoutTemplate,
    layoutEngine: configStore.layoutEngine,
    layoutControlConfig: configStore.layoutControlConfig,
    customColors: configStore.customColors,
    positions: configStore.positions,
    preserveModelOrder: configStore.preserveModelOrder,
    hideLinkLabelTails: configStore.hideLinkLabelTails,
    annotationPanelPosition: configStore.annotationPanelPosition,
    showAnnotationIcons: configStore.showAnnotationIcons,
    assignmentMode: configStore.assignmentMode
  }))
  const diagramData = ref(null)

  // 中心范围的业务对象编码集合
  const centerBoCodes = computed(() => {
    return new Set(centerScope.value || [])
  })

  // 关系范围的业务对象编码集合
  const relationBoCodes = computed(() => {
    return new Set(relationFilteredBoCodes.value || [])
  })

  // 外部关联的业务对象编码集合（关系范围中不在中心范围的）
  const externalBoCodes = computed(() => {
    const external = new Set()
    relationBoCodes.value.forEach(code => {
      if (!centerBoCodes.value.has(code)) {
        external.add(code)
      }
    })
    return external
  })

  // 统计函数：计算给定业务对象集合的统计信息
  const calculateStatsForBoCodes = (boCodes) => {
    if (!previewData.value) {
      return { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 }
    }

    const boCodeSet = new Set(boCodes)

    // 统计领域、子领域、服务模块
    const domains = new Set()
    const subDomains = new Set()
    const serviceModules = new Set()

    previewData.value.domainProducts?.forEach(domain => {
      let domainHasSelected = false
      domain.modules?.forEach(subDomain => {
        let subDomainHasSelected = false
        subDomain.submodules?.forEach(module => {
          let moduleHasSelected = false
          module.businessObjects?.forEach(bo => {
            const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
            if (boCodeSet.has(boCode)) {
              moduleHasSelected = true
              subDomainHasSelected = true
              domainHasSelected = true
            }
          })
          if (moduleHasSelected) {
            serviceModules.add(module.code || module.name)
          }
        })
        if (subDomainHasSelected) {
          subDomains.add(subDomain.name)
        }
      })
      if (domainHasSelected) {
        domains.add(domain.name)
      }
    })

    // 统计业务对象关系
    let objectRelations = 0
    if (previewData.value.relationships) {
      previewData.value.relationships.forEach(rel => {
        if (boCodeSet.has(rel.sourceCode) && boCodeSet.has(rel.targetCode)) {
          objectRelations++
        }
      })
    }

    // 统计服务模块关系（基于业务对象关系推导）
    let serviceModuleRelations = 0
    if (previewData.value.relationships && previewData.value.businessObjects) {
      const boToModuleMap = new Map()
      previewData.value.businessObjects.forEach(bo => {
        if (bo.code) {
          boToModuleMap.set(bo.code, bo.serviceModule)
        }
      })

      const moduleRelationSet = new Set()
      previewData.value.relationships.forEach(rel => {
        if (boCodeSet.has(rel.sourceCode) && boCodeSet.has(rel.targetCode)) {
          const sourceModule = boToModuleMap.get(rel.sourceCode)
          const targetModule = boToModuleMap.get(rel.targetCode)
          if (sourceModule && targetModule && sourceModule !== targetModule) {
            const pair = [sourceModule, targetModule].sort()
            moduleRelationSet.add(`${pair[0]}-${pair[1]}`)
          }
        }
      })
      serviceModuleRelations = moduleRelationSet.size
    }

    return {
      domains: domains.size,
      subDomains: subDomains.size,
      serviceModules: serviceModules.size,
      businessObjects: boCodeSet.size,
      objectRelations,
      serviceModuleRelations
    }
  }

  /**
   * 步骤导航统计计算
   * 
   * 各步骤统计说明：
   * - import: 导入步骤 - 显示导入的总数据量
   * - center: 中心步骤 - 显示中心范围的完整统计（领域、子域、对象）
   * - external: 外部关联统计（全部外部关联）
   * - incremental: 关系步骤 - 显示相比中心新增的统计（带+前缀）
   * - total: 类型步骤 - 显示总数统计（中心+外部）
   * - config: 配置步骤 - 根据图表类型显示不同统计
   *   * 业务对象图：服务模块、对象、关系
   *   * 服务模块图：服务模块、模块关系
   */

  // 过滤后的关系：基于 selectedRelationNodeIds 过滤（需要在 selectedStats 之前定义）
  const filteredRelations = computed(() => {
    return getSelectedRelationCodes(relationCategoryTree.value, selectedRelationNodeIds.value)
  })

  const selectedStats = computed(() => {
    // 导入（总数）
    const importStats = stats.value

    // 中心范围统计
    const centerStats = calculateStatsForBoCodes(Array.from(centerBoCodes.value))

    // 外部关联统计（全部外部）
    const externalStats = calculateStatsForBoCodes(Array.from(externalBoCodes.value))

    // 选择总数 = 中心范围 + 外部关联（并集）
    const selectedBoCodes = new Set([...centerBoCodes.value, ...externalBoCodes.value])
    const totalStats = calculateStatsForBoCodes(Array.from(selectedBoCodes))

    // 计算增量统计 = 总数 - 中心范围（真正的新增部分）
    // 用于关系步骤显示，带+前缀表示相比中心新增
    const incrementalStats = {
      domains: totalStats.domains - centerStats.domains,
      subDomains: totalStats.subDomains - centerStats.subDomains,
      serviceModules: totalStats.serviceModules - centerStats.serviceModules,
      businessObjects: totalStats.businessObjects - centerStats.businessObjects,
      objectRelations: filteredRelations.value.length
    }

    return {
      import: importStats,
      center: centerStats,
      external: externalStats,
      incremental: incrementalStats,  // 新增：增量统计
      total: totalStats
    }
  })

  // 中心范围相关状态
  const centerScopePresets = ref([])    // 中心范围预设列表
  
  // 从 localStorage 加载预设
  const loadPresetsFromStorage = () => {
    try {
      const stored = localStorage.getItem('centerScopePresets')
      if (stored) {
        centerScopePresets.value = JSON.parse(stored)
        console.log('[useDiagramData] Loaded presets from storage:', centerScopePresets.value.length)
      }
    } catch (e) {
      console.error('[useDiagramData] Failed to load presets from storage:', e)
    }
  }
  
  // 保存预设到 localStorage
  const savePresetsToStorage = () => {
    try {
      localStorage.setItem('centerScopePresets', JSON.stringify(centerScopePresets.value))
      console.log('[useDiagramData] Saved presets to storage:', centerScopePresets.value.length)
    } catch (e) {
      console.error('[useDiagramData] Failed to save presets to storage:', e)
    }
  }
  
  // 初始化时加载预设
  loadPresetsFromStorage()
  const relationScope = ref({           // 关系范围选择
    internal: {
      'cross-domain': false,
      'same-domain-cross-subdomain': false,
      'same-subdomain-cross-module': false,
      'same-module': false
    },
    external: {
      'cross-domain': false,
      'same-domain-cross-subdomain': false,
      'same-subdomain-cross-module': false,
      'same-module': false
    }
  })
  const selectedRelationNodeIds = ref([]) // 选中的关系分类节点ID
  const isInitializedFromArchData = ref(false)

  const availableSubDomains = computed(() => {
    if (!previewData.value?.domainProducts) return []

    // 中心范围 + 关系范围（并集）
    const centerBoCodes = centerScope.value ? new Set(centerScope.value) : new Set()
    const relationBoCodes = relationFilteredBoCodes.value ? new Set(relationFilteredBoCodes.value) : new Set()

    const allBoCodes = new Set([...centerBoCodes, ...relationBoCodes])

    if (allBoCodes.size === 0) {
      return extractSubDomains(previewData.value.domainProducts)
    }

    const subDomains = new Set()

    previewData.value.businessObjects.forEach(bo => {
      if (allBoCodes.has(bo.code) && bo.subDomain) {
        subDomains.add(bo.subDomain)
      }
    })

    return Array.from(subDomains)
  })

  // 中心范围标识信息：存储领域、子领域和服务模块是否为中心范围
  // 注意：只基于 centerScope（用户在步骤1选择的中心范围），不包含关系范围
  const centerScopeMarkers = computed(() => configStore.centerScopeMarkers)

  let updateCallId = 0

  function updateCenterScopeMarkers() {
    const callId = ++updateCallId
    const markers = {
      domains: new Map(),
      subDomains: new Map(),
      serviceModules: new Map()
    }

    // 只使用 centerScope，不使用 relationFilteredBoCodes
    // 因为颜色判断只应该基于用户选择的中心范围
    const centerScopeSet = new Set(centerScope.value || [])

    // 如果 centerScope 为空，清空 markers
    if (centerScopeSet.size === 0) {
      configStore.updateCenterScopeMarkers(markers)
      return
    }

    // 使用 previewData.value.serviceModules 来获取正确的服务模块名称
    // 因为 filteredContainers 也使用 serviceModules 来构建节点数据
    if (previewData.value?.serviceModules) {
      previewData.value.serviceModules.forEach(sm => {
        // 检查这个服务模块是否包含中心范围的业务对象
        const matchingBos = previewData.value.businessObjects?.filter(
          bo => bo.serviceModule === sm.code && centerScopeSet.has(bo.code)
        )
        if (matchingBos && matchingBos.length > 0) {
          // 存储服务模块的 name 和 code
          if (sm.name) {
            markers.serviceModules.set(sm.name, true)
          }
          if (sm.code) {
            markers.serviceModules.set(sm.code, true)
          }
        }
      })
    }

    // 检查是否有过时的调用
    if (callId !== updateCallId) {
      return
    }

    // 仍然保留 domainProducts 的遍历来更新 domains 和 subDomains
    if (previewData.value?.domainProducts) {
      previewData.value.domainProducts.forEach(domain => {
        let domainHasCenter = false

        domain.modules?.forEach(subDomain => {
          let subDomainHasCenter = false

          subDomain.submodules?.forEach(module => {
            module.businessObjects?.forEach(bo => {
              const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
              if (centerScopeSet.has(boCode)) {
                subDomainHasCenter = true
                domainHasCenter = true
              }
            })
          })

          markers.subDomains.set(subDomain.name, subDomainHasCenter)
        })

        markers.domains.set(domain.name, domainHasCenter)
      })
    }

    configStore.updateCenterScopeMarkers(markers)
    return markers
  }

  const availableDomains = computed(() => {
    if (!previewData.value?.domainProducts) return []

    // 中心范围 + 关系范围（并集）
    const centerBoCodes = centerScope.value ? new Set(centerScope.value) : new Set()
    const relationBoCodes = relationFilteredBoCodes.value ? new Set(relationFilteredBoCodes.value) : new Set()

    const allBoCodes = new Set([...centerBoCodes, ...relationBoCodes])

    if (allBoCodes.size === 0) {
      return previewData.value.domainProducts.map(domain => domain.name)
    }

    const domains = new Set()

    previewData.value.businessObjects.forEach(bo => {
      if (allBoCodes.has(bo.code) && bo.domain) {
        domains.add(bo.domain)
      }
    })

    return Array.from(domains)
  })

  const availableServiceModules = computed(() => {
    if (!previewData.value?.serviceModules) return []

    // 中心范围 + 关系范围（并集）
    const centerBoCodes = centerScope.value ? new Set(centerScope.value) : new Set()
    const relationBoCodes = relationFilteredBoCodes.value ? new Set(relationFilteredBoCodes.value) : new Set()

    const allBoCodes = new Set([...centerBoCodes, ...relationBoCodes])

    if (allBoCodes.size === 0) {
      return previewData.value.serviceModules
    }

    const serviceModuleCodes = new Set()

    previewData.value.businessObjects.forEach(bo => {
      if (allBoCodes.has(bo.code) && bo.serviceModule) {
        serviceModuleCodes.add(bo.serviceModule)
      }
    })

    return previewData.value.serviceModules.filter(sm => serviceModuleCodes.has(sm.code))
  })

  const filteredContainers = computed(() => {
    if (!previewData.value) return []

    // 最终显示范围 = 中心范围 ∪ 关系新增（并集，不会减少，只会新增）
    const centerScopeSet = new Set(centerScope.value || [])
    const relationSet = new Set(relationFilteredBoCodes.value || [])
    const finalBoCodes = new Set([...centerScopeSet, ...relationSet])

    if (chartType.value === 'serviceModule') {
      const subDomainMap = new Map()

      if (previewData.value.serviceModules) {
        previewData.value.serviceModules.forEach(sm => {
          // 显示范围 = centerScope ∪ relationFilteredBoCodes，只要有关联就显示
          const hasAnyBo = previewData.value.businessObjects.some(
            bo => bo.serviceModule === sm.code && finalBoCodes.has(bo.code)
          )
          if (!hasAnyBo) return

          if (!subDomainMap.has(sm.subDomain)) {
            const domain = previewData.value.domainProducts?.find(
              d => d.modules?.some(m => m.name === sm.subDomain)
            )
            const subDomainModule = domain?.modules?.find(m => m.name === sm.subDomain)
            subDomainMap.set(sm.subDomain, {
              id: sm.subDomain,
              name: sm.subDomain,
              code: subDomainModule?.code || sm.subDomain,
              fullTitle: domain ? `${domain.name} / ${sm.subDomain}` : sm.subDomain,
              domain: domain ? domain.name : '未分类',
              domainCode: domain ? (domain.code || domain.name) : '未分类',
              subDomainName: sm.subDomain,
              nodes: []
            })
          }
          subDomainMap.get(sm.subDomain).nodes.push({
            id: sm.code,
            name: sm.name,
            code: sm.code
          })
        })
      }

      return [...subDomainMap.values()]
    }

    if (previewData.value.domainProducts) {
      const containers = []
      const businessObjects = previewData.value.businessObjects || []

      previewData.value.domainProducts.forEach(domain => {
        if (domain.modules) {
          domain.modules.forEach(module => {
            // 显示范围 = centerScope ∪ relationFilteredBoCodes
            const hasAnyBo = businessObjects.some(
              bo => bo.subDomain === module.name && finalBoCodes.has(bo.code)
            )
            if (!hasAnyBo) return

            const moduleBusinessObjects = businessObjects.filter(
              bo => bo.subDomain === module.name && finalBoCodes.has(bo.code)
            )

            if (moduleBusinessObjects.length === 0) return

            const serviceModuleMap = new Map()
            moduleBusinessObjects.forEach(bo => {
              const smCode = bo.serviceModule || bo.smCode || '未分类'
              const smName = bo.serviceModuleName || smCode || '未分类'
              if (!serviceModuleMap.has(smName)) {
                serviceModuleMap.set(smName, {
                  code: smCode,
                  name: smName,
                  nodes: []
                })
              }
              serviceModuleMap.get(smName).nodes.push({
                id: bo.name,
                name: bo.name,
                code: bo.code,
                serviceModuleName: smName,
                serviceModule: smCode
              })
            })

            containers.push({
              id: module.code || module.name,
              name: module.name,
              fullTitle: domain.name + ' / ' + module.name,
              domain: domain.name,
              domainCode: domain.code || domain.name,
              subDomainName: module.name,
              nodes: moduleBusinessObjects.map(bo => {
                const smCode = bo.serviceModule || bo.smCode || '未分类'
                const smName = bo.serviceModuleName || smCode || '未分类'
                return {
                  id: bo.name,
                  name: bo.name,
                  code: bo.code,
                  serviceModuleName: smName,
                  serviceModule: smCode
                }
              }),
              serviceModuleMap: Object.fromEntries(serviceModuleMap)
            })
          })
        }
      })
      return containers
    }
    return []
  })

  const filteredDomainProducts = computed(() => {
    if (!previewData.value?.domainProducts) return []

    const centerScopeSet = new Set(centerScope.value || [])
    const relationSet = new Set(relationFilteredBoCodes.value || [])
    const finalBoCodes = new Set([...centerScopeSet, ...relationSet])
    const hasFilter = finalBoCodes.size > 0

    const filteredDomainProducts = []

    previewData.value.domainProducts.forEach(domain => {
      const filteredDomain = {
        name: domain.name,
        code: domain.code || domain.name,
        isCenter: false,
        modules: []
      }

      domain.modules?.forEach(subDomain => {
        const filteredSubDomain = {
          name: subDomain.name,
          code: subDomain.code || subDomain.name,
          isCenter: false,
          submodules: []
        }

        subDomain.submodules?.forEach(sm => {
          const hasAnyBo = previewData.value.businessObjects.some(
            bo => bo.serviceModule === sm.code && finalBoCodes.has(bo.code)
          )
          if (!hasFilter || hasAnyBo) {
            filteredSubDomain.submodules.push({
              ...sm,
              isCenter: hasFilter && centerScopeSet.size > 0
                ? previewData.value.businessObjects.some(
                    bo => bo.serviceModule === sm.code && centerScopeSet.has(bo.code)
                  )
                : false
            })
          }
        })

        if (filteredSubDomain.submodules.length > 0) {
          filteredSubDomain.isCenter = filteredSubDomain.submodules.some(sm => sm.isCenter)
          filteredDomain.modules.push(filteredSubDomain)
        }
      })

      if (filteredDomain.modules.length > 0) {
        filteredDomain.isCenter = filteredDomain.modules.some(m => m.isCenter)
        filteredDomainProducts.push(filteredDomain)
      }
    })

    return filteredDomainProducts
  })

  const stats = computed(() => {
    if (!previewData.value) {
      return {
        domains: 0,
        subDomains: 0,
        serviceModules: 0,
        businessObjects: 0,
        objectRelations: 0,
        serviceModuleRelations: 0
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

    const objectRelations = previewData.value.relationships?.length || 0
    const serviceModuleRelations = computedServiceModuleRelations(
      previewData.value.relationships,
      previewData.value.businessObjects,
      previewData.value.serviceModules
    ).length

    return { domains, subDomains, serviceModules, businessObjects, objectRelations, serviceModuleRelations }
  })

  // 新的显示统计格式：导入、中心范围、外部关联、选择总数
  const displayStats = computed(() => {
    // 根据图表类型计算配置步骤的统计
    const configStats = (() => {
      if (chartType.value === 'serviceModule') {
        const totalStats = selectedStats.value.total
        return {
          serviceModules: totalStats.serviceModules,
          serviceModuleRelations: filteredRelations.value.length || 0
        }
      } else {
        const totalStats = selectedStats.value.total
        return {
          serviceModules: totalStats.serviceModules,
          businessObjects: totalStats.businessObjects,
          domains: totalStats.domains,
          subDomains: totalStats.subDomains,
          objectRelations: filteredRelations.value.length || 0
        }
      }
    })()

    return {
      import: stats.value,
      center: selectedStats.value.center || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      external: selectedStats.value.external || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      incremental: selectedStats.value.incremental || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      total: {
        ...selectedStats.value.total,
        objectRelations: filteredRelations.value.length || 0
      },
      config: configStats
    }
  })

  // 关系分类树：基于 centerScope 和 previewData.relationships 计算
  const relationCategoryTree = computed(() => {
    console.log('[relationCategoryTree] computed triggered')
    console.log('[relationCategoryTree] previewData.relationships:', previewData.value?.relationships?.length)
    console.log('[relationCategoryTree] previewData.businessObjects:', previewData.value?.businessObjects?.length)
    console.log('[relationCategoryTree] centerScope type:', typeof centerScope.value, 'isArray:', Array.isArray(centerScope.value))
    console.log('[relationCategoryTree] centerScope length:', centerScope.value?.length)

    if (!previewData.value?.relationships || !previewData.value?.businessObjects) {
      return []
    }

    // 运行数据校验，获取问题关系编码
    const validationResult = validateData(rawData.value, previewData.value)
    const invalidRelationCodes = new Set()
    validationResult.items.forEach(item => {
      if (item.sheet === '业务对象关系' && item.entityCode) {
        invalidRelationCodes.add(item.entityCode)
      }
    })

    // 过滤掉问题关系
    let validRelationships = previewData.value.relationships
    if (invalidRelationCodes.size > 0) {
      validRelationships = previewData.value.relationships.filter(rel => !invalidRelationCodes.has(rel.relationCode))
    }

    return buildRelationCategoryTree(
      validRelationships,
      centerScope.value,
      previewData.value.businessObjects
    )
  })

  const generateDiagram = () => {
    if (!previewData.value) {
      return
    }

    if (diagramConfig.value.hideLinkLabelTails === null) {
      configStore.updateHideLinkLabelTails(diagramConfig.value.layoutEngine === 'elk')
    }

    // 最终显示范围 = 中心范围 ∪ 关系新增（并集，不会减少，只会新增）
    let finalBoCodes = new Set(centerScope.value || [])
    
    if (relationFilteredBoCodes.value && relationFilteredBoCodes.value.length > 0) {
      relationFilteredBoCodes.value.forEach(code => finalBoCodes.add(code))
    }

    const hasFilter = finalBoCodes && finalBoCodes.size > 0

    // 计算业务对象的 isCenter 标识
    // isCenter 只取决于是否在 centerScope 中，与 relationFilteredBoCodes 无关
    const centerScopeSet = new Set(centerScope.value || [])
    const filteredBusinessObjects = hasFilter
      ? previewData.value.businessObjects.filter(bo => finalBoCodes.has(bo.code)).map(bo => ({
          ...bo,
          isCenter: centerScopeSet.has(bo.code)  // 只有在 centerScope 中的才是 isCenter
        }))
      : previewData.value.businessObjects.map(bo => ({
          ...bo,
          isCenter: false
        }))

    // 计算服务模块的 isCenter 标识
    const smBoCountMap = new Map()
    previewData.value.businessObjects.forEach(bo => {
      if (bo.serviceModule) {
        if (!smBoCountMap.has(bo.serviceModule)) {
          smBoCountMap.set(bo.serviceModule, { total: 0, center: 0 })
        }
        smBoCountMap.get(bo.serviceModule).total++
        if (finalBoCodes?.has(bo.code)) {
          smBoCountMap.get(bo.serviceModule).center++
        }
      }
    })

    const filteredServiceModules = hasFilter
      ? previewData.value.serviceModules.filter(sm => {
          const smData = smBoCountMap.get(sm.code)
          return smData && smData.total > 0
        }).map(sm => {
          const smData = smBoCountMap.get(sm.code)
          // 包含中心范围的业务对象即为 isCenter（与 ServiceModuleConfig 一致）
          return {
            ...sm,
            isCenter: smData.center > 0
          }
        })
      : previewData.value.serviceModules.map(sm => ({
          ...sm,
          isCenter: false
        }))

    // 计算子领域的 isCenter 标识
    const subDomainSmCenterMap = new Map()
    filteredServiceModules.forEach(sm => {
      if (!subDomainSmCenterMap.has(sm.subDomain)) {
        subDomainSmCenterMap.set(sm.subDomain, { total: 0, center: 0 })
      }
      subDomainSmCenterMap.get(sm.subDomain).total++
      if (sm.isCenter) {
        subDomainSmCenterMap.get(sm.subDomain).center++
      }
    })

    // 计算领域的 isCenter 标识（基于过滤后的子领域）
    const domainSubDomainCenterMap = new Map()
    subDomainSmCenterMap.forEach((sdData, sdName) => {
      // 找到这个子领域属于哪个领域
      previewData.value.domainProducts?.forEach(domain => {
        const subDomain = domain.modules?.find(sd => sd.name === sdName)
        if (subDomain) {
          if (!domainSubDomainCenterMap.has(domain.name)) {
            domainSubDomainCenterMap.set(domain.name, { total: 0, center: 0 })
          }
          domainSubDomainCenterMap.get(domain.name).total++
          if (sdData.center === sdData.total && sdData.total > 0) {
            domainSubDomainCenterMap.get(domain.name).center++
          }
        }
      })
    })

    // 运行数据校验，获取问题关系编码
    const validationResult = validateData(rawData.value, previewData.value)
    const invalidRelationCodes = new Set()
    validationResult.items.forEach(item => {
      if (item.sheet === '业务对象关系' && item.entityCode) {
        invalidRelationCodes.add(item.entityCode)
      }
    })

    // 过滤关系：先按范围过滤，再排除问题关系
    let filteredRelationships = hasFilter
      ? previewData.value.relationships.filter(rel =>
          finalBoCodes.has(rel.sourceCode) && finalBoCodes.has(rel.targetCode)
        )
      : previewData.value.relationships

    // 排除校验发现的问题关系
    if (invalidRelationCodes.size > 0) {
      filteredRelationships = filteredRelationships.filter(rel => !invalidRelationCodes.has(rel.relationCode))
    }

    // 根据关系范围选择过滤关系
    const selectedRelationCodes = filteredRelations.value
    if (hasFilter) {
      if (selectedRelationCodes && selectedRelationCodes.length > 0) {
        filteredRelationships = filteredRelationships.filter(rel => selectedRelationCodes.includes(rel.relationCode))
      } else {
        filteredRelationships = []
      }
    }

    const finalRelationships = internalRelationFilter.value === 'off'
      ? filteredRelationships
      : filteredRelationships.filter(rel => {
          const sourceBo = filteredBusinessObjects.find(bo => bo.code === rel.sourceCode)
          const targetBo = filteredBusinessObjects.find(bo => bo.code === rel.targetCode)
          if (sourceBo && targetBo) {
            let isInternal = false
            if (internalRelationFilter.value === 'serviceModule') {
              isInternal = sourceBo.serviceModule === targetBo.serviceModule
            } else if (internalRelationFilter.value === 'subDomain') {
              isInternal = sourceBo.subDomain === targetBo.subDomain
            } else if (internalRelationFilter.value === 'domain') {
              isInternal = sourceBo.domain === targetBo.domain
            }
            return !isInternal
          }
          return true
        })

    // 过滤服务模块（只包含选中业务对象所属的服务模块）
    const filteredSmCodes = new Set()
    filteredBusinessObjects.forEach(bo => {
      if (bo.serviceModule) {
        filteredSmCodes.add(bo.serviceModule)
      }
    })

    // 过滤领域产品结构（已在上方计算）
    const filteredDomainProducts = []
    if (hasFilter) {
      previewData.value.domainProducts.forEach(domain => {
        const domainData = domainSubDomainCenterMap.get(domain.name)
        const filteredDomain = {
          name: domain.name,
          isCenter: domainData ? domainData.center === domainData.total && domainData.total > 0 : false,
          modules: []
        }
        domain.modules?.forEach(subDomain => {
          const sdData = subDomainSmCenterMap.get(subDomain.name)
          const filteredSubDomain = {
            name: subDomain.name,
            isCenter: sdData ? sdData.center === sdData.total && sdData.total > 0 : false,
            submodules: []
          }
          subDomain.submodules?.forEach(sm => {
            if (filteredSmCodes.has(sm.code)) {
              const smData = smBoCountMap.get(sm.code)
              const filteredSm = {
                ...sm,
                isCenter: smData ? smData.center === smData.total && smData.total > 0 : false,
                businessObjects: sm.businessObjects?.filter(bo => {
                  const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
                  return finalBoCodes.has(boCode)
                }) || []
              }
              if (filteredSm.businessObjects.length > 0) {
                filteredSubDomain.submodules.push(filteredSm)
              }
            }
          })
          if (filteredSubDomain.submodules.length > 0) {
            filteredDomain.modules.push(filteredSubDomain)
          }
        })
        if (filteredDomain.modules.length > 0) {
          filteredDomainProducts.push(filteredDomain)
        }
      })
    } else {
      previewData.value.domainProducts.forEach(domain => {
        const filteredDomain = {
          name: domain.name,
          isCenter: false,
          modules: []
        }
        domain.modules?.forEach(subDomain => {
          const filteredSubDomain = {
            name: subDomain.name,
            isCenter: false,
            submodules: []
          }
          subDomain.submodules?.forEach(sm => {
            const filteredSm = {
              ...sm,
              isCenter: false
            }
            filteredSubDomain.submodules.push(filteredSm)
          })
          filteredDomain.modules.push(filteredSubDomain)
        })
        filteredDomainProducts.push(filteredDomain)
      })
    }

    if (chartType.value === 'serviceModule') {
      // 从业务对象关系计算服务模块关系
      const serviceModuleRelationships = computedServiceModuleRelations(
        finalRelationships,
        filteredBusinessObjects,
        filteredServiceModules
      )

      // 获取中心范围的服务模块编码（用于服务模块图过滤）
      const centerServiceModuleCodes = new Set()
      if (centerScope.value && centerScope.value.length > 0) {
        // 从中心范围的业务对象找到对应的服务模块
        const centerBoCodes = new Set(centerScope.value)
        filteredBusinessObjects.forEach(bo => {
          if (centerBoCodes.has(bo.code) && bo.serviceModule) {
            centerServiceModuleCodes.add(bo.serviceModule)
          }
        })
      }

      // 过滤服务模块关系：只保留与中心服务模块相关的关系
      const filteredServiceModuleRelationships = centerServiceModuleCodes.size > 0
        ? serviceModuleRelationships.filter(rel =>
            centerServiceModuleCodes.has(rel.sourceServiceModuleCode) ||
            centerServiceModuleCodes.has(rel.targetServiceModuleCode)
          )
        : serviceModuleRelationships

      // 过滤服务模块：只保留涉及的服务模块
      const involvedServiceModuleCodes = new Set()
      filteredServiceModuleRelationships.forEach(rel => {
        involvedServiceModuleCodes.add(rel.sourceServiceModuleCode)
        involvedServiceModuleCodes.add(rel.targetServiceModuleCode)
      })
      const finalFilteredServiceModules = centerServiceModuleCodes.size > 0
        ? filteredServiceModules.filter(sm => involvedServiceModuleCodes.has(sm.code))
        : filteredServiceModules

      const useLegacy = diagramConfig.value.useLegacyGroupControl

      if (!useLegacy) {
        // 服务模块图使用过滤后的数据，与业务对象图一致
        // 配置阶段基于过滤后的数据模型（中心范围 + 关系选择）
        const architectureData = {
          domainProducts: filteredDomainProducts,
          businessObjects: filteredBusinessObjects,
          serviceModules: finalFilteredServiceModules
        }

        // 服务模块图使用与业务对象图相同的分组构建逻辑
        // 这样可以确保 userConfig.groups 和 architectureGroups 结构一致
        let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.SERVICE_MODULE)

        // 服务模块图不过滤分组，保留所有服务模块用于显示
        // 中心范围标记通过 centerScopeMarkers.serviceModules 处理，用于高亮显示
        // 只有当用户明确要求只显示中心范围时才过滤（目前不支持此功能）

        const userConfig = diagramConfig.value.layoutControlConfig
        const groupModel = GroupModel.fromUserConfig(architectureGroups, userConfig, ChartType.SERVICE_MODULE)

        const mermaidConfig = groupModel.toMermaidConfig()
        const groupControlTitleMap = mermaidConfig.titleMap || {}

        const hasValidUserConfig = userConfig && userConfig.groups && userConfig.groups.length > 0

        // 始终使用 mermaidConfig，因为它包含了合并后的分组结构
        // mermaidConfig 是从 GroupModel.fromUserConfig(architectureGroups, userConfig) 生成的
        // 已经合并了用户配置中的启用/禁用状态
        const layoutControlConfig = mermaidConfig

        // 重要：将生成的 layoutControlConfig 更新到 store
        configStore.updateLayoutControlConfig(layoutControlConfig)

        // 从 filteredContainers 提取服务模块数据（与配置页面保持一致）
        // filteredContainers 是按子领域分组的服务模块结构，包含 nodes 数组
        const smFromContainers = []
        filteredContainers.value.forEach(subDomainItem => {
          subDomainItem.nodes?.forEach(sm => {
            smFromContainers.push({
              ...sm,
              subDomain: subDomainItem.name,
              domain: subDomainItem.domain
            })
          })
        })

        diagramData.value = buildServiceModuleDiagramData({
          serviceModules: smFromContainers,
          serviceModuleRelationships: filteredServiceModuleRelationships,
          domainProducts: filteredDomainProducts,
          centerSubDomain: diagramConfig.value.centerDomain,
          centerSubDomainColor: diagramConfig.value.centerDomainColor,
          centerScopeColor: diagramConfig.value.centerScopeColor,
          serviceModuleBgColor: diagramConfig.value.serviceModuleBgColor,
          colorGroupBy: diagramConfig.value.colorGroupBy,
          colorScheme: diagramConfig.value.colorScheme,
          serviceModuleTextColor: diagramConfig.value.serviceModuleTextColor,
          layoutTemplate: diagramConfig.value.layoutTemplate,
          customColors: diagramConfig.value.customColors || {},
          hideLinkLabelTails: diagramConfig.value.hideLinkLabelTails,
          layoutControlConfig: layoutControlConfig,
          groupControlTitleMap: groupControlTitleMap,
          centerServiceModuleCodes: centerServiceModuleCodes.size > 0 ? Array.from(centerServiceModuleCodes) : null,
          centerScopeHighlight: diagramConfig.value.centerScopeHighlight
        })

        if (configStore.useUnifiedRenderer) {
          const colorResult = ColorCalculator.compute({
            nodes: smFromContainers.map(sm => ({
              code: sm.code,
              domain: sm.domain,
              subDomain: sm.subDomain,
              isCenter: diagramConfig.value.centerScopeHighlight && centerServiceModuleCodes.has(sm.code)
            })),
            colorGroupBy: diagramConfig.value.colorGroupBy,
            colorScheme: diagramConfig.value.colorScheme,
            centerScopeColor: diagramConfig.value.centerScopeColor,
            customColors: diagramConfig.value.customColors || {},
            centerScopeHighlight: diagramConfig.value.centerScopeHighlight
          })

          const annotationMap = new Map()
          smFromContainers.forEach(sm => {
            if (sm.annotationContent) {
              annotationMap.set(sm.code, { category: sm.annotationCategory, content: sm.annotationContent })
            }
          })

          enrichGroupModel(groupModel, ChartType.SERVICE_MODULE, {
            colorMap: colorResult.colorMap,
            containerColorMap: colorResult.groupColorMap,
            centerCodes: centerServiceModuleCodes,
            annotationMap,
            nodeTextColor: diagramConfig.value.serviceModuleTextColor || 'black'
          })

          const unifiedLinks = filteredServiceModuleRelationships.map(rel => ({
            source: rel.sourceServiceModuleCode,
            target: rel.targetServiceModuleCode,
            label: rel.serviceRelationshipCode,
            relationCode: rel.serviceRelationshipCode,
            annotationCategory: rel.annotationCategory || 'info',
            annotationContent: rel.annotationContent || ''
          }))

          const unifiedMermaidCode = UnifiedRenderer.render(
            groupModel, unifiedLinks, ChartType.SERVICE_MODULE,
            { layoutEngine: diagramConfig.value.layoutEngine }
          )

          console.log('[UnifiedRenderer] SM mermaid code generated, length:', unifiedMermaidCode.length)

          diagramData.value._unifiedMermaidCode = unifiedMermaidCode
        }
      } else {
        // 服务模块图（旧模型）- deprecated
        const legacyConfig = buildLegacyLayoutControlConfig(filteredDomainProducts, filteredContainers.value, diagramConfig.value.layoutControlConfig)
        diagramData.value = buildServiceModuleDiagramData({
          serviceModules: filteredServiceModules,
          serviceModuleRelationships: serviceModuleRelationships,
          domainProducts: filteredDomainProducts,
          centerSubDomain: diagramConfig.value.centerDomain,
          centerSubDomainColor: diagramConfig.value.centerDomainColor,
          serviceModuleBgColor: diagramConfig.value.serviceModuleBgColor,
          colorGroupBy: diagramConfig.value.colorGroupBy,
          colorScheme: diagramConfig.value.colorScheme,
          serviceModuleTextColor: diagramConfig.value.serviceModuleTextColor,
          layoutTemplate: diagramConfig.value.layoutTemplate,
          customColors: diagramConfig.value.customColors || {},
          hideLinkLabelTails: diagramConfig.value.hideLinkLabelTails,
          layoutControlConfig: legacyConfig
        })
      }
    } else {
      // 业务对象图
      const useLegacy = diagramConfig.value.useLegacyGroupControl

      if (!useLegacy) {
        // ========== 使用 GroupModel ==========
        const architectureData = {
          domainProducts: filteredDomainProducts,
          businessObjects: filteredBusinessObjects,
          serviceModules: filteredServiceModules
        }

        // 1. 从架构数据构建分组
        let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.BUSINESS_OBJECT)

        // 2. 应用范围过滤
        if (hasFilter && finalBoCodes) {
          architectureGroups = filterGroupModelByScope(architectureGroups, finalBoCodes, ChartType.BUSINESS_OBJECT)
        }

        // 3. 创建 GroupModel 并合并用户配置
        const userConfig = diagramConfig.value.layoutControlConfig
        const groupModel = GroupModel.fromUserConfig(architectureGroups, userConfig, ChartType.BUSINESS_OBJECT)

        // 4. 直接生成 Mermaid 配置（包含扁平化和标题处理）
        const layoutControlConfig = groupModel.toMermaidConfig()

        // 5. 使用旧模型的 buildDiagramData，复用所有渲染逻辑
        diagramData.value = buildDiagramData({
          businessObjects: filteredBusinessObjects,
          relationships: finalRelationships,
          domainProducts: filteredDomainProducts,
          serviceModules: filteredServiceModules,
          colorGroupBy: diagramConfig.value.colorGroupBy,
          centerScopeColor: diagramConfig.value.centerScopeColor,
          colorScheme: diagramConfig.value.colorScheme,
          nodeTextColor: diagramConfig.value.nodeTextColor,
          centerScope: centerScope.value,
          layoutTemplate: diagramConfig.value.layoutTemplate,
          customColors: diagramConfig.value.customColors || {},
          hideLinkLabelTails: diagramConfig.value.hideLinkLabelTails,
          layoutControlConfig: layoutControlConfig,
          centerScopeHighlight: diagramConfig.value.centerScopeHighlight
        })

        if (configStore.useUnifiedRenderer) {
          const colorResult = ColorCalculator.compute({
            nodes: filteredBusinessObjects.map(bo => ({
              code: bo.code,
              domain: bo.domain,
              subDomain: bo.subDomain,
              serviceModule: bo.serviceModule,
              isCenter: bo.isCenter || false
            })),
            colorGroupBy: diagramConfig.value.colorGroupBy,
            colorScheme: diagramConfig.value.colorScheme,
            centerScopeColor: diagramConfig.value.centerScopeColor,
            customColors: diagramConfig.value.customColors || {},
            centerScopeHighlight: diagramConfig.value.centerScopeHighlight
          })

          const annotationMap = new Map()
          filteredBusinessObjects.forEach(bo => {
            if (bo.annotationContent) {
              annotationMap.set(bo.code, { category: bo.annotationCategory, content: bo.annotationContent })
            }
          })

          const centerCodes = new Set(centerScope.value || [])

          enrichGroupModel(groupModel, ChartType.BUSINESS_OBJECT, {
            colorMap: colorResult.colorMap,
            containerColorMap: colorResult.groupColorMap,
            centerCodes,
            annotationMap,
            nodeTextColor: diagramConfig.value.nodeTextColor || 'black'
          })

          const unifiedLinks = finalRelationships.map(rel => ({
            source: rel.sourceCode,
            target: rel.targetCode,
            label: rel.relationDesc,
            relationCode: rel.relationCode,
            annotationCategory: rel.annotationCategory || 'info',
            annotationContent: rel.annotationContent || ''
          }))

          const unifiedMermaidCode = UnifiedRenderer.render(
            groupModel, unifiedLinks, ChartType.BUSINESS_OBJECT,
            { layoutEngine: diagramConfig.value.layoutEngine }
          )

          console.log('[UnifiedRenderer] BO mermaid code generated, length:', unifiedMermaidCode.length)

          diagramData.value._unifiedMermaidCode = unifiedMermaidCode
        }
      } else {
        // ========== 旧模型：保持原有逻辑 ==========
        // 使用用户配置的分组（如果有），否则自动构建
        const legacyConfig = buildLegacyLayoutControlConfig(filteredDomainProducts, filteredContainers.value, diagramConfig.value.layoutControlConfig)

        diagramData.value = buildDiagramData({
          businessObjects: filteredBusinessObjects,
          relationships: finalRelationships,
          domainProducts: filteredDomainProducts,
          serviceModules: filteredServiceModules,
          colorGroupBy: diagramConfig.value.colorGroupBy,
          centerScopeColor: diagramConfig.value.centerScopeColor,
          colorScheme: diagramConfig.value.colorScheme,
          nodeTextColor: diagramConfig.value.nodeTextColor,
          centerScope: centerScope.value,
          layoutTemplate: diagramConfig.value.layoutTemplate,
          customColors: diagramConfig.value.customColors || {},
          hideLinkLabelTails: diagramConfig.value.hideLinkLabelTails,
          layoutControlConfig: legacyConfig
        })
      }
    }
  }

  const filterByRelation = (boCodes) => {
    if (!boCodes) {
      // 关闭关系过滤
      relationFilteredBoCodes.value = null
      return
    }
    if (boCodes.length === 0) {
      relationFilteredBoCodes.value = []
      return
    }
    relationFilteredBoCodes.value = boCodes
  }

  const setInternalRelationFilter = (filter) => {
    internalRelationFilter.value = filter
  }

  // 监听图表类型变化
  watch(chartType, (newType, oldType) => {
    if (oldType !== undefined && newType !== oldType) {
      configStore.updatePreviousChartType(oldType)
      configStore.setChartTypeChanged(true)
      configStore.updateLayoutControlConfig({
        enabled: false,
        overallDirection: 'LR',
        groups: [],
        engine: 'elk',
        preserveOrder: true
      })
    }
  })

  const resetChartTypeChanged = () => {
    configStore.resetChartTypeChanged()
  }

  // 切换关系节点选中状态
  const toggleRelationNode = (nodeId) => {
    const index = selectedRelationNodeIds.value.indexOf(nodeId)
    if (index === -1) {
      selectedRelationNodeIds.value.push(nodeId)
    } else {
      selectedRelationNodeIds.value.splice(index, 1)
    }
  }

  // 保存中心范围预设
  const saveCenterScopePreset = (nameOrData) => {
    // 兼容两种调用方式：saveCenterScopePreset(name) 或 saveCenterScopePreset({ name, selectedIds })
    let name, selectedIds
    if (typeof nameOrData === 'object' && nameOrData !== null) {
      name = nameOrData.name
      selectedIds = nameOrData.selectedIds
    } else {
      name = nameOrData
    }
    
    if (!name || !name.trim()) {
      console.warn('[useDiagramData] 预设名称不能为空')
      return null
    }

    const preset = {
      id: `preset-${Date.now()}`,
      name: name.trim(),
      centerScope: selectedIds ? [...selectedIds] : [...centerScope.value],
      relationScope: JSON.parse(JSON.stringify(relationScope.value)),
      selectedRelationNodeIds: [...selectedRelationNodeIds.value],
      createdAt: new Date().toISOString()
    }

    centerScopePresets.value.push(preset)
    savePresetsToStorage() // 保存到 localStorage
    return preset
  }

  // 加载中心范围预设
  const loadCenterScopePreset = (presetId) => {
    const preset = centerScopePresets.value.find(p => p.id === presetId)
    if (!preset) {
      console.warn('[useDiagramData] 未找到预设:', presetId)
      return false
    }

    centerScope.value = [...preset.centerScope]
    relationScope.value = JSON.parse(JSON.stringify(preset.relationScope))
    selectedRelationNodeIds.value = [...preset.selectedRelationNodeIds]
    return true
  }

  // 删除中心范围预设
  const deleteCenterScopePreset = (presetId) => {
    const index = centerScopePresets.value.findIndex(p => p.id === presetId)
    if (index === -1) {
      console.warn('[useDiagramData] 未找到要删除的预设:', presetId)
      return false
    }

    centerScopePresets.value.splice(index, 1)
    savePresetsToStorage() // 保存到 localStorage
    console.log('[useDiagramData] 已删除预设:', presetId)
    return true
  }

  // 清空关系范围选择
  const clearRelationScope = () => {
    relationScope.value = {
      internal: {
        'cross-domain': false,
        'same-domain-cross-subdomain': false,
        'same-subdomain-cross-module': false,
        'same-module': false
      },
      external: {
        'cross-domain': false,
        'same-domain-cross-subdomain': false,
        'same-subdomain-cross-module': false,
        'same-module': false
      }
    }
    selectedRelationNodeIds.value = []
  }

  let lastCustomColorsStr = ''
  watch(
    () => {
      const cc = diagramConfig.value?.customColors
      return cc ? JSON.stringify(cc) : ''
    },
    (newStr) => {
      if (newStr !== lastCustomColorsStr) {
        lastCustomColorsStr = newStr
        if (previewData.value && newStr) {
          generateDiagram()
        }
      }
    }
  )

  watch(
    () => diagramConfig.value?.colorScheme,
    (newScheme, oldScheme) => {
      if (newScheme !== oldScheme && previewData.value) {
        generateDiagram()
      }
    }
  )

  watch(
    () => diagramConfig.value?.colorGroupBy,
    (newGroupBy, oldGroupBy) => {
      if (newGroupBy !== oldGroupBy && previewData.value) {
        generateDiagram()
      }
    }
  )

  watch(
    () => diagramConfig.value?.centerScopeHighlight,
    (newHighlight, oldHighlight) => {
      if (newHighlight !== oldHighlight && previewData.value) {
        generateDiagram()
      }
    }
  )

  watch(
    centerScope,
    (newScope, oldScope) => {
      if (diagramData.value && newScope !== oldScope) {
        diagramData.value = null
      }
      updateCenterScopeMarkers()
    }
  )

  watchEffect(() => {
    if (centerScope.value && centerScope.value.length > 0 && previewData.value?.domainProducts) {
      updateCenterScopeMarkers()
    }
  })

  watch(
    () => diagramConfig.value?.layoutEngine,
    (newEngine, oldEngine) => {
      if (newEngine !== oldEngine && oldEngine !== undefined) {
        configStore.updateHideLinkLabelTails(null)
      }
    }
  )

  const resetData = () => {
    clearData()
    centerScope.value = []
    relationFilteredBoCodes.value = null
    internalRelationFilter.value = 'off'
    diagramData.value = null
    selectedStats.value = {
      domains: 0,
      subDomains: 0,
      serviceModules: 0,
      businessObjects: 0,
      objectRelations: 0,
      serviceModuleRelations: 0
    }
  }

  async function initFromArchDataManager(archData) {
    const { versionId, hierarchyFilter, relationTypeFilter } = archData
    
    loading.value = true
    try {
      const result = await buildPreviewDataFromArchData(null, versionId, hierarchyFilter)
      
      previewData.value = {
        domainProducts: result.allDomainProducts || result.domainProducts,
        businessObjects: result.allBusinessObjects || result.businessObjects,
        serviceModules: result.allServiceModules || result.serviceModules,
        relationships: result.relationships
      }
      
      // 直接使用 buildPreviewDataFromArchData 返回的 centerScope，避免重复 API 调用
      const centerScopeCodes = result.centerScope || []
      configStore.updateCenterScope(centerScopeCodes)
      
      if (relationTypeFilter && relationTypeFilter.length > 0) {
        selectedRelationNodeIds.value = convertToRelationNodeIds(relationTypeFilter)
      }
      
      isInitializedFromArchData.value = true
      
      updateCenterScopeMarkers()
      
      rawData.value = {
        businessObjectData: previewData.value.businessObjects || [],
        serviceComponentData: previewData.value.serviceModules || [],
        relationshipData: previewData.value.relationships || []
      }
      
      await nextTick()
      
      if (relationTypeFilter && relationTypeFilter.length > 0) {
        const relationCodesFilter = new Set(relationTypeFilter)
        
        const nodeIds = []
        function findNodeIdsForCodes(node) {
          if (node.relationCodes && node.relationCodes.length > 0) {
            const hasMatchingCode = node.relationCodes.some(code => relationCodesFilter.has(code))
            if (hasMatchingCode) {
              nodeIds.push(node.id)
            }
          }
          if (node.children && node.children.length > 0) {
            node.children.forEach(child => findNodeIdsForCodes(child))
          }
        }
        
        if (relationCategoryTree.value) {
          relationCategoryTree.value.forEach(rootNode => findNodeIdsForCodes(rootNode))
        }
        
        if (nodeIds.length > 0) {
          selectedRelationNodeIds.value = nodeIds
        }
      } else {
        const allCategoryNodeIds = []
        function collectCategoryNodeIds(node) {
          if (node.scopeType && node.categoryType) {
            allCategoryNodeIds.push(node.id)
          }
          if (node.children && node.children.length > 0) {
            node.children.forEach(child => collectCategoryNodeIds(child))
          }
        }
        if (relationCategoryTree.value) {
          relationCategoryTree.value.forEach(rootNode => {
            if (rootNode.children) {
              rootNode.children.forEach(child => collectCategoryNodeIds(child))
            }
          })
        }
        if (allCategoryNodeIds.length > 0) {
          selectedRelationNodeIds.value = allCategoryNodeIds
        }
      }
      
      if (selectedRelationNodeIds.value && selectedRelationNodeIds.value.length > 0) {
        const relationCodes = new Set(getSelectedRelationCodes(relationCategoryTree.value, selectedRelationNodeIds.value))
        
        const filteredCodes = new Set(centerScopeCodes)
        
        if (previewData.value.relationships) {
          previewData.value.relationships.forEach(rel => {
            if (relationCodes.has(rel.relationCode)) {
              filteredCodes.add(rel.sourceCode)
              filteredCodes.add(rel.targetCode)
            }
          })
        }
        
        relationFilteredBoCodes.value = Array.from(filteredCodes)
      }
      
      loading.value = false
    } catch (error) {
      console.error('[useDiagramData] Failed to initialize from arch data:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    // 状态
    loading,
    error,
    previewData,
    rawData,
    centerScope,
    selectedScope,
    relationFilteredBoCodes,
    chartType,
    chartTypeChanged,
    previousChartType,
    diagramConfig,
    diagramData,
    selectedStats,
    centerScopePresets,
    relationScope,
    selectedRelationNodeIds,
    isInitializedFromArchData,

    // 计算属性
    availableSubDomains,
    availableDomains,
    availableServiceModules,
    centerScopeMarkers,
    filteredContainers,
    filteredDomainProducts,
    stats,
    displayStats,
    relationCategoryTree,
    filteredRelations,

    // 方法
    handleFileUpload,
    generateDiagram,
    filterByRelation,
    setInternalRelationFilter,
    resetChartTypeChanged,
    resetData,
    toggleRelationNode,
    saveCenterScopePreset,
    loadCenterScopePreset,
    clearRelationScope,
    initFromArchDataManager
  }
}
