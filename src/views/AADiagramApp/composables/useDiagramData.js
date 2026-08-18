import { ref, computed, watch, watchEffect, nextTick } from 'vue'
import { useExcelParser } from '../../../composables/useExcelParser.js'
import { useDiagramConfigStore } from '../../../stores/diagramConfigStore.js'
import { useChartArchDataStore } from '../../../stores/chartArchDataStore'
import { apiV2 } from '@/utils/httpClient'
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
  getSelectedRelationCodes,
  getSelectedRelationIds
} from '../../../services/relationClassifier.js'
import { buildPreviewDataFromArchData, convertToRelationNodeIds } from '../../../services/archDataConverter.js'
// [DEFAULT-LEVEL 2026-08-12] applyDefaultExpandByScope 已废弃: 初始展开层级
// 由渲染层 EmbeddedChartView 按分组数量自适应 (applyDefaultExpandByCount) 决定,
// 此处在生成阶段套用范围折叠会与自适应展开冲突, 故不再引入。

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
      overallDirection: 'TB',
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
  // [FIX 2026-08-03] BO 编码 → 名称映射, 用于回填子关系的 sourceName/targetName
  //   (后端 *_bo_name 列 V863 全 NULL, 见 archDataConverter.js L225 注释,
  //    子关系 tooltip 需 BO 名称展示, 必须从 businessObjects 反查)
  const boCodeToNameMap = new Map()
  businessObjects.forEach(bo => {
    if (bo.code) {
      boToModuleMap.set(bo.code, {
        moduleCode: bo.serviceModule,
        moduleName: bo.serviceModuleName || bo.serviceModule
      })
      boCodeToNameMap.set(bo.code, bo.name || '')
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

    // [FIX 2026-08-03] SM 关系 tooltip 展示所有子关系:
    //   每条 BO 级关系作为一个子关系 entry, 携带完整元数据 (source/target name+code,
    //   type/direction/desc/annotations), 供下游 useTooltip 逐条渲染.
    //   之前只存 annotationContent/Category, 缺少 BO 名称/类型/方向/desc →
    //   tooltip 只能拼字符串, 无法展示"所有子关系 BO 对列表".
    //   去重: 同 boRelCode 只入一次 (避免一对 BO 多条 annotation 导致重复 entry)
    const alreadyHasBoRel = relation.businessObjectRelationships.some(r => r.relationCode === boRelCode)
    if (!alreadyHasBoRel) {
      relation.businessObjectRelationships.push({
        relationCode: boRelCode,
        code: rel.code || '',
        sourceCode: rel.sourceCode || '',
        // [FIX 2026-08-03] 后端 *_bo_name 列全 NULL, 从 businessObjects 反查 BO 名称
        sourceName: rel.sourceName || boCodeToNameMap.get(rel.sourceCode) || '',
        targetCode: rel.targetCode || '',
        targetName: rel.targetName || boCodeToNameMap.get(rel.targetCode) || '',
        relationType: rel.relationType || '',
        relationDirection: rel.relationDirection || '',
        relationDesc: rel.relationDesc || '',
        annotationContents: rel.annotationContents || [],
        annotationCategories: rel.annotationCategories || []
      })
    }
  })

  // 处理备注内容
  const result = []
  moduleRelationMap.forEach((rel) => {
    // 去重后的业务对象关系编码
    const uniqueBoCodes = [...new Set(rel.businessObjectRelationshipCodes.filter(Boolean))]

    // [FIX 2026-08-03] 兼容老消费方: 从子关系数组的 annotationContents/Categories 拼出
    //   单字符串 annotationContent + 首个 annotationCategory.
    //   新消费方 (useTooltip) 直接读 businessObjectRelationships 数组逐条渲染.
    const annotationParts = []
    const allCategories = []
    rel.businessObjectRelationships.forEach(boRel => {
      const contents = boRel.annotationContents || []
      const categories = boRel.annotationCategories || []
      contents.forEach((content, idx) => {
        if (!content) return
        const code = boRel.relationCode || ''
        annotationParts.push(code ? `${content} ${code}` : content)
        allCategories.push(categories[idx] || 'info')
      })
    })
    const uniqueAnnotations = [...new Set(annotationParts)]

    // [FIX 2026-08-03] SM 聚合关系方向推导:
    //   - 任一子关系是 BIDIRECTIONAL/双向 → SM 关系双向 (用户期望: 子关系双向则 SM 连线也双向)
    //   - 否则取首个非空子关系方向 (全部同向时取该方向; 混合方向如推+拉保持首个)
    //   - 同时透传首个非空 relationType (tooltip 父关系概览展示)
    //   之前 result 没有 relationDirection/relationType 字段 →
    //   serviceModuleDiagramBuilder 透传空值 → getArrowSyntax 永远渲染 --> 单向
    //   [缺口4 2026-08-03] 混合方向 (推+拉共存, 无双向) 时 console.warn, 便于排查方向推导异常.
    let smRelationDirection = ''
    let smRelationType = ''
    const _seenDirections = new Set()
    for (const boRel of rel.businessObjectRelationships) {
      const dir = boRel.relationDirection
      if (dir === 'BIDIRECTIONAL' || dir === '双向') {
        smRelationDirection = 'BIDIRECTIONAL'
        break
      }
      if (!smRelationDirection && dir) {
        smRelationDirection = dir
      }
      if (dir) _seenDirections.add(dir)
    }
    // 缺口4: 混合方向 (>=2 种不同单向方向, 无双向) 时 warn
    if (_seenDirections.size > 1 && smRelationDirection !== 'BIDIRECTIONAL') {
      console.warn('[useDiagramData] SM 关系 %s 子关系方向混合 (%s), 取首个 %s',
        `${rel.sourceServiceModuleCode}-${rel.targetServiceModuleCode}`,
        [..._seenDirections].join('/'), smRelationDirection)
    }
    for (const boRel of rel.businessObjectRelationships) {
      if (boRel.relationType) {
        smRelationType = boRel.relationType
        break
      }
    }

    result.push({
      sourceServiceModuleCode: rel.sourceServiceModuleCode,
      sourceServiceModuleName: rel.sourceServiceModuleName,
      targetServiceModuleCode: rel.targetServiceModuleCode,
      targetServiceModuleName: rel.targetServiceModuleName,
      serviceRelationshipCode: `${rel.sourceServiceModuleCode}-${rel.targetServiceModuleCode}`,
      businessObjectRelationshipCodes: uniqueBoCodes,
      // [FIX 2026-08-03] 完整子关系数组, 供下游 tooltip 展示"所有子关系 BO 对列表"
      businessObjectRelationships: rel.businessObjectRelationships,
      // [FIX 2026-08-03] 透传推导出的方向/类型, 供 getArrowSyntax 渲染双向连线
      relationDirection: smRelationDirection,
      relationType: smRelationType,
      annotationContent: uniqueAnnotations.join('; ') || '',
      annotationCategory: allCategories[0] || 'info'
    })
  })

  return result
}

export function useDiagramData() {
  const { loading, error, previewData, rawData, handleFileUpload, clearData } = useExcelParser()
  const configStore = useDiagramConfigStore()
  window.__configStore = configStore

  // [2026-06-15] 架构数据图表缓存 store (diagramData 缓存用)
  const chartArchStore = useChartArchDataStore()

  const centerScope = computed(() => configStore.centerScope)
  const selectedScope = ref([])
  // 关键修复 v27: relationFilteredBoCodes 已改为 computed (见 line 372)
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
    // [FIX 2026-06-29 v3] 加上 annotationCategoryFilter
    //   之前漏了这行, 传给 StepDisplay/MermaidComponent 的 annotationConfig 没有 filter 字段
    //   useSvgProcessor.renderAnnotationOverlay 拿 annotationConfig.annotationCategoryFilter 时是 undefined
    //   → || [] → 永远空数组 → 永远不过滤
    // 主线不受影响: 默认 [] = 不过滤 (向后兼容)
    annotationCategoryFilter: configStore.annotationCategoryFilter,
    assignmentMode: configStore.assignmentMode
  }))
  const diagramData = ref(null)
  // [FIX 2026-08-02] 当前版本 ID: 统一管道 L1 树缓存 key 组成部分 (spec 4.4)
  const currentVersionId = ref(0)

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
  // 关键修复 v26：返回 unique 关系 ID（不是 unique relationCode）
  // 之前返回 unique relationCode，导致同一类型的多条关系被算成 1 个
  // （如 4 条 CONTAINS 算成 1 条），所以架构管理显示 29 → chart 只显示 21
  // 关键修复 v29：补全跨域关系 (src⊕tgt, 如 TEST600→BO_WAREHOUSE)
  //   收紧条件: 仅当用户主动选了 INTERNAL 或 CROSS_BOUNDARY 节点时才补全
  //   保护"用户只选 INTERNAL 不想引入外部"语义
  // [V1.2.9 修复] 优先使用 archRelationIds (从 chartData 传入的精确关系 IDs)
  //   反向匹配按叶子 module 节点选中, 但叶子节点的 relationIds 可能包含用户未选的关系
  //   (例如: 用户选"同子领域跨服务模块"分类下 2 个关系, 但 module 节点 relationIds 是 3 个)
  //   直接用 archRelationIds 避免反向匹配的过度匹配
  //   fallback: 用户在图表页手动操作时, 仍可用 getSelectedRelationIds
  const archRelationIdsRef = ref(null)

  // [PERF 2026-08-13] 基础 previewData 快照 (首次 init 时的对象范围数据)。
  //   关系范围变更时 (对象范围不变) 从此快照恢复, 避免重新拉取 architecture/preview,
  //   同时清理上次补全累积的外部 BO (避免 previewData 越滚越大)。
  const basePreviewData = ref(null)

  // [PERF 2026-08-13] 上次渲染的领域数量 (用于检测关系范围变更是否引入新的领域层级)。
  //   领域数变化 (如从 1 个领域 → 多个领域) 时, 应重置展开层级状态, 让渲染层重新自适应默认展开。
  const lastFilteredDomainCount = ref(0)

  const filteredRelations = computed(() => {
    if (archRelationIdsRef.value && archRelationIdsRef.value.length > 0) {
      return [...archRelationIdsRef.value]
    }
    return getSelectedRelationIds(relationCategoryTree.value, selectedRelationNodeIds.value)
  })

  // 关键修复 v27: 关系范围对应的 BO 集合, 必须跟随 filteredRelations 实时计算
  // 之前在 initFromArchDataManager 中只计算一次, 用户切换 category 选择时不会更新
  // 现象: 用户取消勾选 external scope, filteredRelations 28, 但 rfb 仍含 TEST600 (26)
  // 修复: 改为 computed, 依赖 filteredRelations + centerScope + previewData
  const relationFilteredBoCodes = computed(() => {
    const centerScopeCodes = new Set(centerScope.value || [])
    const filteredCodes = new Set(centerScopeCodes)
    const relationIds = new Set(filteredRelations.value || [])
    if (previewData.value?.relationships) {
      // [V1.2.9 修复] 只采纳用户选中的关系引入 BO codes
      // 之前 [V1.1.13] 有兜底: 用户未勾选时拉所有 cross-boundary 关系的 BO codes
      //   → 即使用户没勾选任何关系, 也会强行引入所有外部 BO, 图表统计和渲染与关系范围选择脱钩
      // 现在: 严格按用户选中的关系 (filteredRelations) 引入 BO
      //   取消所有勾选时, relationFilteredBoCodes = centerScope (即图表只显示中心 BO, 没有任何外部 BO)
      previewData.value.relationships.forEach(rel => {
        if (relationIds.has(rel.id)) {
          if (rel.sourceCode) filteredCodes.add(rel.sourceCode)
          if (rel.targetCode) filteredCodes.add(rel.targetCode)
        }
      })
    }
    return Array.from(filteredCodes)
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
    // 关键修复 v32: objectRelations 用 total - center 而非 filteredRelations.length
    // 因为 filteredRelations 可能漏掉 1 条 (e.g. 后端算 CROSS_BOUNDARY 但前端 src/tgt 都不在 centerScope
    //   → 不入 tree → fromTree 没收集 → relationFilteredBoCodes 漏 1 BO)
    // 用 total - center 总是与中心范围的实际显示关系数对齐:
    //   center 5 (INTERNAL) + 增量 8 (CROSS_BOUNDARY) = 总 13, 与管理页 5+8=13 一致
    const incrementalStats = {
      domains: totalStats.domains - centerStats.domains,
      subDomains: totalStats.subDomains - centerStats.subDomains,
      serviceModules: totalStats.serviceModules - centerStats.serviceModules,
      businessObjects: totalStats.businessObjects - centerStats.businessObjects,
      externalBusinessObjects: externalBoCodes.value.size,  // v29: 跨域关系引入的范围外端 BO 数
      objectRelations: totalStats.objectRelations - centerStats.objectRelations,
      serviceModuleRelations: totalStats.serviceModuleRelations - centerStats.serviceModuleRelations
    }

    // [DEBUG 2026-06-15 临时探针] 只读不写, 业务逻辑无任何修改
    // 启用方式: 浏览器 console 执行 window.__diagDebug = true 后重现问题
    // 关闭: window.__diagDebug = false
    if (typeof window !== 'undefined' && window.__diagDebug) {
      try {
        const pd = previewData.value || {}
        console.groupCollapsed('[diag] selectedStats breakdown')
        console.log('centerBoCodes 数量:', centerBoCodes.value?.size, '前 10:', Array.from(centerBoCodes.value || []).slice(0, 10))
        console.log('externalBoCodes 数量:', externalBoCodes.value?.size, '内容:', Array.from(externalBoCodes.value || []))
        console.log('selectedBoCodes (并集) 数量:', selectedBoCodes.size)
        console.log('previewData.businessObjects 总数:', pd.businessObjects?.length)
        console.log('previewData.relationships 总数:', pd.relationships?.length)
        console.log('previewData.domainProducts 顶层数:', pd.domainProducts?.length)
        if (pd.domainProducts?.length) {
          const d0 = pd.domainProducts[0]
          console.log('  domainProducts[0]:', { name: d0?.name, modules数: d0?.modules?.length })
          if (d0?.modules?.length) {
            const sd0 = d0.modules[0]
            console.log('  domainProducts[0].modules[0]:', { name: sd0?.name, submodules数: sd0?.submodules?.length })
            if (sd0?.submodules?.length) {
              const sm0 = sd0.submodules[0]
              console.log('  domainProducts[0].modules[0].submodules[0]:', { name: sm0?.name, BO数: sm0?.businessObjects?.length })
            }
          }
        }
        console.log('centerStats  :', centerStats)
        console.log('totalStats   :', totalStats)
        console.log('incremental  :', incrementalStats)
        console.log('差值对比 (total - center):', {
          domains: totalStats.domains - centerStats.domains,
          subDomains: totalStats.subDomains - centerStats.subDomains,
          serviceModules: totalStats.serviceModules - centerStats.serviceModules,
          businessObjects: totalStats.businessObjects - centerStats.businessObjects,
          objectRelations: totalStats.objectRelations - centerStats.objectRelations,
        })
        console.groupEnd()
      } catch (e) { /* debug only, swallow */ }
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

    // [BUG-V033 修复 2026-06-29] 颜色配置应显示 "中心 ∪ 关系范围" 的所有子领域
    //   - CenterDomainSelect 内部 isFullyInCenterScope 会自动过滤完全在中心的 (用 centerScopeColor)
    //   - 剩下外部的分配颜色组合
    //   - 之前误改成只用 centerScope → 外部项被过滤 → 颜色项缺失
    //   - relationFilteredBoCodes = centerScope + 用户选中的关系引入的 BO (BUG-V032 已修复, 不再全量)
    // [BUG-V033 二轮修复 2026-06-29] relationFilteredBoCodes 返回 Array (非 Set), 用 .length 而非 .size
    const allBoCodes = relationFilteredBoCodes.value && relationFilteredBoCodes.value.length > 0
      ? new Set(relationFilteredBoCodes.value)
      : (centerScope.value ? new Set(centerScope.value) : new Set())

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
      serviceModules: new Map(),
      // [PARTIAL-CENTER 2026-08-15] 完全包含对象范围标记 (该分组所有 BO 都在 centerScope):
      //   fullyServiceModules / fullySubDomains / fullyDomains: key → 是否完全包含.
      //   与 hasCenter 标记配合区分三种折叠节点着色:
      //     hasCenter && fully → centerScopeColor; hasCenter && !fully → 中性灰; !hasCenter → 分组色.
      //   兼容旧契约: 原 domains/subDomains/serviceModules 仍按布尔/仅含中心 SM 语义填充.
      fullyDomains: new Map(),
      fullySubDomains: new Map(),
      fullyServiceModules: new Map()
    }

    // 只使用 centerScope，不使用 relationFilteredBoCodes
    // 因为颜色判断只应该基于用户选择的中心范围
    const centerScopeSet = new Set(centerScope.value || [])

    // 如果 centerScope 为空，清空 markers
    if (centerScopeSet.size === 0) {
      configStore.updateCenterScopeMarkers(markers)
      return
    }

    // [PARTIAL-CENTER 2026-08-15] 按层级聚合 BO 计数 (total/center) — 数据源与旧逻辑一致 (previewData).
    //   分组"完全包含对象范围" = 该分组所有【图表内】BO (finalBoCodes = centerScope ∪ 关系引入外部 BO)
    //   都在 centerScope 中, 即: 有中心 BO 且无"关系引入的外部 BO".
    //   关键: 外部 BO 判定基于 relationFilteredBoCodes (用户选中关系真正引入图表的 BO),
    //   而非 previewData 全量窗口 — 否则 SCP-only (无外部 BO) 时 供应链云 领域因 previewData
    //   含其他子领域 BO 被误判"部分包含"→ 折叠节点错误中性 (与语法层 collectDescendantBoCodes
    //   按图表分组树判定完全包含的结果不一致, 见 2026-08-15 验证).
    const externalBoSet = new Set()
    ;(relationFilteredBoCodes.value || []).forEach(code => {
      if (!centerScopeSet.has(code)) externalBoSet.add(code)
    })
    const smCounts = new Map()       // sm.code -> { total, center, external }
    const sdCounts = new Map()       // subDomain.name -> { total, center, external }
    const domainCounts = new Map()   // domain.name -> { total, center, external }
    const bump = (map, key, isCenter, isExternal) => {
      if (!key) return
      const c = map.get(key) || { total: 0, center: 0, external: 0 }
      c.total++
      if (isCenter) c.center++
      if (isExternal) c.external++
      map.set(key, c)
    }
    ;(previewData.value?.businessObjects || []).forEach(bo => {
      const isCenter = centerScopeSet.has(bo.code)
      const isExternal = externalBoSet.has(bo.code)
      bump(smCounts, bo.serviceModule, isCenter, isExternal)
      bump(sdCounts, bo.subDomain, isCenter, isExternal)
      bump(domainCounts, bo.domain, isCenter, isExternal)
    })

    // 使用 previewData.value.serviceModules 来获取正确的服务模块名称
    // 因为 filteredContainers 也使用 serviceModules 来构建节点数据
    if (previewData.value?.serviceModules) {
      previewData.value.serviceModules.forEach(sm => {
        const c = smCounts.get(sm.code)
        const hasCenter = !!c && c.center > 0
        const fullyCenter = !!c && c.center > 0 && c.external === 0
        if (hasCenter) {
          // 存储服务模块的 name 和 code
          if (sm.name) {
            markers.serviceModules.set(sm.name, true)
          }
          if (sm.code) {
            markers.serviceModules.set(sm.code, true)
          }
        }
        if (sm.name) {
          markers.fullyServiceModules.set(sm.name, fullyCenter)
        }
        if (sm.code) {
          markers.fullyServiceModules.set(sm.code, fullyCenter)
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
        let domainAllCenter = true
        let domainTotal = 0

        domain.modules?.forEach(subDomain => {
          const sdCount = sdCounts.get(subDomain.name)
          const subDomainHasCenter = !!sdCount && sdCount.center > 0
          const subDomainAllCenter = !!sdCount && sdCount.center > 0 && sdCount.external === 0

          markers.subDomains.set(subDomain.name, subDomainHasCenter)
          markers.fullySubDomains.set(subDomain.name, subDomainAllCenter)

          if (subDomainHasCenter) domainHasCenter = true
          if (!subDomainAllCenter) domainAllCenter = false
          domainTotal += (sdCount?.total || 0)
        })

        markers.domains.set(domain.name, domainHasCenter)
        markers.fullyDomains.set(domain.name, domainAllCenter && domainTotal > 0)
      })
    }

    configStore.updateCenterScopeMarkers(markers)
    return markers
  }

  const availableDomains = computed(() => {
    if (!previewData.value?.domainProducts) return []

    // [BUG-V033 修复] 颜色配置显示 "中心 ∪ 关系范围" 的所有领域
    // [BUG-V033 二轮修复] relationFilteredBoCodes 返回 Array, 用 .length
    const allBoCodes = relationFilteredBoCodes.value && relationFilteredBoCodes.value.length > 0
      ? new Set(relationFilteredBoCodes.value)
      : (centerScope.value ? new Set(centerScope.value) : new Set())

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
    if (!previewData.value?.businessObjects?.length) return []

    // [BUG-V033 修复] 颜色配置显示 "中心 ∪ 关系范围" 的所有服务模块
    //   - CenterDomainSelect 内部 isFullyInCenterScope 自动过滤完全在中心的
    //   - 剩下外部的分配颜色
    // [BUG-V033 二轮修复] relationFilteredBoCodes 返回 Array, 用 .length
    const allBoCodes = relationFilteredBoCodes.value && relationFilteredBoCodes.value.length > 0
      ? new Set(relationFilteredBoCodes.value)
      : (centerScope.value ? new Set(centerScope.value) : new Set())

    const smMap = new Map()

    if (allBoCodes.size === 0) {
      // 兜底: 全量返回
      previewData.value.businessObjects.forEach(bo => {
        const name = bo.serviceModuleName || bo.serviceModule
        const code = bo.serviceModule || bo.serviceModuleName
        if (name && !smMap.has(name)) {
          smMap.set(name, { name, code: code || name })
        }
      })
      return Array.from(smMap.values())
    }

    previewData.value.businessObjects.forEach(bo => {
      if (allBoCodes.has(bo.code)) {
        const name = bo.serviceModuleName || bo.serviceModule
        const code = bo.serviceModule || bo.serviceModuleName
        if (name && !smMap.has(name)) {
          smMap.set(name, { name, code: code || name })
        }
      }
    })
    return Array.from(smMap.values())
  })

  const filteredContainers = computed(() => {
    if (!previewData.value) return []

    // [V1.2.9 修复] 最终显示范围 = 中心范围 ∪ 用户选中的关系引入的外部 BO
    // 之前 [V1.1.13] 有兜底: 当 relationFilteredBoCodes 不含外部 BO 时,
    //   从 previewData 拉所有 cross-boundary 关系, 强行引入外部 BO
    //   → 取消所有关系勾选时, 图表仍然包含所有外部 BO, 统计和渲染与关系范围选择脱钩
    // 现在: 严格按 relationFilteredBoCodes (已严格依赖 selectedRelationNodeIds)
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
            code: sm.code,
            // [FIX 2026-06-29] 透传 annotation 数组字段
            //   之前只 push id/name/code, annotation 字段全丢, 图表显示没数字标记
            //   archDataConverter 输出 sm.annotationContents/Categories 是数组
            annotationContents: sm.annotationContents || [],
            annotationCategories: sm.annotationCategories || []
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

    // [V1.2.9 修复] 移除 [V1.1.13] 跨域兜底: 直接用 relationFilteredBoCodes
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

    // v29: 补齐范围外 BO 的层级 (domain/subDomain/serviceModule)
    //      如果 BO 在 finalBoCodes 但其层级不在 formal domainProducts 中，
    //      为其创建 synthetic hierarchy entries → 确保 groupModel 有容器 + ColorCalculator 有颜色
    if (hasFilter) {
      const placedBoCodes = new Set()
      filteredDomainProducts.forEach(domain => {
        domain.modules?.forEach(sd => {
          sd.submodules?.forEach(sm => {
            previewData.value.businessObjects.forEach(bo => {
              if (bo.serviceModule === sm.code && finalBoCodes.has(bo.code)) {
                placedBoCodes.add(bo.code)
              }
            })
          })
        })
      })

      // 收集未放置的 BO 的层级信息
      const orphanHierarchy = new Map() // domainName -> subDomainName -> smCode -> {name, codes[]}
      previewData.value.businessObjects.forEach(bo => {
        if (finalBoCodes.has(bo.code) && !placedBoCodes.has(bo.code)) {
          const domainName = bo.domain || '其他领域'
          const subDomainName = bo.subDomain || '其他子领域'
          const smCode = bo.serviceModule || bo.serviceModuleName || '其他服务模块'
          const smName = bo.serviceModuleName || bo.serviceModule || smCode

          if (!orphanHierarchy.has(domainName)) {
            orphanHierarchy.set(domainName, new Map())
          }
          const sdMap = orphanHierarchy.get(domainName)
          if (!sdMap.has(subDomainName)) {
            sdMap.set(subDomainName, new Map())
          }
          const smMap = sdMap.get(subDomainName)
          if (!smMap.has(smCode)) {
            smMap.set(smCode, { name: smName, codes: [] })
          }
          smMap.get(smCode).codes.push(bo.code)
        }
      })

      // 将 orphan hierarchy 合并到 filteredDomainProducts
      orphanHierarchy.forEach((sdMap, domainName) => {
        // 查找或创建 domain
        let domainEntry = filteredDomainProducts.find(d => d.name === domainName)
        if (!domainEntry) {
          domainEntry = {
            name: domainName,
            code: domainName,
            isCenter: false,
            modules: []
          }
          filteredDomainProducts.push(domainEntry)
        }

        sdMap.forEach((smMap, subDomainName) => {
          let sdEntry = domainEntry.modules.find(sd => sd.name === subDomainName)
          if (!sdEntry) {
            sdEntry = {
              name: subDomainName,
              code: subDomainName,
              isCenter: false,
              submodules: []
            }
            domainEntry.modules.push(sdEntry)
          }

          smMap.forEach((smInfo, smCode) => {
            let smEntry = sdEntry.submodules.find(sm => sm.code === smCode)
            if (!smEntry) {
              smEntry = {
                name: smInfo.name,
                code: smCode,
                isCenter: false,
                businessObjects: smInfo.codes
              }
              sdEntry.submodules.push(smEntry)
            }
          })
        })
      })
    }

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
  // v39.6: 重构 total/config 计算 - total = center + incremental (与"总数 = 中心∪关系"语义一致)
  // 之前: total.objectRelations = filteredRelations.length (只含 relation tree 选中)
  //   → 丢失中心范围的 4 条关系, 总数显示 8 而非 12
  // 之后: total = center + incremental, config = total (口径完全一致)
  const displayStats = computed(() => {
    // 关键修复 v37: 服务模块图也用完整 5 指标 (与业务对象图统一)
    // 关键修复 v38: objectRelations 跟 displayStats.total.objectRelations 口径一致
    // 关键修复 v39.6: total = center + incremental, config = total
    // 先计算 center / incremental / external, 再算 total
    const center = (() => {
      const base = selectedStats.value.center || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 }
      if (!relationCategoryTree.value) return base
      // [V1.2.9 修复] center.objectRelations 必须采纳用户的关系范围选择
      // 之前: 遍历整棵树, 收集所有 INTERNAL 节点 relationIds, 不看用户选没选
      //   且 gather(根节点) 会收集所有子孙 relationIds → 用户只选 1 个叶子节点也会统计全部
      // 现在: 直接用 filteredRelations (用户选中的关系 IDs) + previewData.relationships.scopeType
      //   只统计用户选中的 internal 关系数
      const selectedIds = selectedRelationNodeIds.value || []
      // 用户在关系范围里完全没选 → 中心范围关系就是 0
      if (selectedIds.length === 0) {
        return { ...base, objectRelations: 0 }
      }
      const userSelectedRelationIds = new Set(filteredRelations.value || [])
      if (userSelectedRelationIds.size === 0) {
        return { ...base, objectRelations: 0 }
      }
      // 统计用户选中的 internal 关系数
      let internalCount = 0
      if (previewData.value?.relationships) {
        previewData.value.relationships.forEach(rel => {
          if (!userSelectedRelationIds.has(rel.id)) return
          // scopeType 为 internal → 中心范围关系
          if (rel.scopeType === 'internal') {
            internalCount++
          }
        })
      }
      return { ...base, objectRelations: internalCount }
    })()

    // [V1.2.9 修复] external 容器统计必须采纳用户的关系范围选择
    // 之前: externalBoCodes 为空时, 强行从 previewData 拉所有 cross-boundary 关系
    //       提取外部 BO codes, 完全无视用户没勾选关系的情况
    // 现在: externalBoCodes 为空时, 用用户实际选中的关系 ID 过滤 previewData
    //       只采纳用户选中的 cross-boundary 关系引入的外部 BO
    //       用户在关系范围里完全没选 → external 全 0
    const external = (() => {
      const base = selectedStats.value.external || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 }
      if (externalBoCodes.value.size > 0) return base
      if (!previewData.value?.relationships) return base
      const selectedIds = selectedRelationNodeIds.value || []
      // 用户在关系范围里完全没选 → external 容器统计为 0
      if (selectedIds.length === 0) return base
      const centerSet = new Set(centerScope.value || [])
      // 用用户选中的关系 ID 过滤 previewData, 只采纳用户选中的 cross-boundary
      const userSelectedIds = new Set(filteredRelations.value || [])
      const crossRels = previewData.value.relationships.filter(r => {
        if (r.sourceCode === r.targetCode) return false
        if (!userSelectedIds.has(r.id)) return false
        if (r.scopeType === 'cross-boundary') return true
        const srcIn = centerSet.has(r.sourceCode)
        const tgtIn = centerSet.has(r.targetCode)
        return srcIn !== tgtIn
      })
      if (crossRels.length === 0) return base
      const externalCodes = new Set()
      crossRels.forEach(r => {
        if (!centerSet.has(r.sourceCode) && r.sourceCode) externalCodes.add(r.sourceCode)
        if (!centerSet.has(r.targetCode) && r.targetCode) externalCodes.add(r.targetCode)
      })
      if (externalCodes.size === 0) return base
      return calculateStatsForBoCodes(Array.from(externalCodes))
    })()

    // 关键修复 v32 (终版): incremental.objectRelations = total - center (都用 selectedNodeIds 口径)
    // 关键修复 v33: 但当 relationCategoryTree 缺失 cross-boundary 节点 (后端 scopeType 错算为
    //   external) 时, 上面的 total - center 永远是 0. 改用 previewData + 后端 scopeType 兜底:
    //   1) 若 relationCategoryTree 中有 cross-boundary 节点 + relationIds, 仍用 total - center
    //   2) 否则直接用 previewData.relationships 中 scopeType=cross-boundary 的关系 ID 数
    const incremental = (() => {
      const base = selectedStats.value.incremental || { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 }
      // [V1.2.9 修复] incremental 同样必须采纳用户的关系范围选择
      // 之前: cbCollect 遍历整棵树, 对 cross-boundary 根节点 gather → 收集所有 cross-boundary 关系
      //   且兜底分支 (incFromTree === 0) 还会无视空选择拉所有 cross-boundary
      // 现在: 直接用 filteredRelations (用户选中的关系 IDs) + previewData.relationships.scopeType
      //   只统计用户选中的 cross-boundary 关系数
      const selectedIds = selectedRelationNodeIds.value || []
      // 用户在关系范围里完全没选 → incremental 直接为 0, 不再走任何兜底
      if (selectedIds.length === 0) {
        return { ...base, objectRelations: 0 }
      }
      const userSelectedRelationIds = new Set(filteredRelations.value || [])
      if (userSelectedRelationIds.size === 0) {
        return { ...base, objectRelations: 0 }
      }
      // 统计用户选中的 cross-boundary 关系数
      let crossCount = 0
      if (previewData.value?.relationships) {
        previewData.value.relationships.forEach(rel => {
          if (!userSelectedRelationIds.has(rel.id)) return
          // scopeType 为 cross-boundary → 通过关系引入的关系
          if (rel.scopeType === 'cross-boundary') {
            crossCount++
          }
        })
      }
      // 容器统计 (domains/subDomains/serviceModules/businessObjects) 来自 external,
      // 来自用户选中的 cross-boundary 关系引入的外部 BO
      const incRelCount = crossCount
      if (incRelCount > 0 && base.domains === 0 && base.subDomains === 0 &&
        base.serviceModules === 0 && base.businessObjects === 0) {
        return {
          domains: external.domains,
          subDomains: external.subDomains,
          serviceModules: external.serviceModules,
          businessObjects: external.businessObjects,
          externalBusinessObjects: external.businessObjects,
          objectRelations: incRelCount,
          serviceModuleRelations: external.serviceModuleRelations || 0
        }
      }
      return { ...base, objectRelations: incRelCount || base.objectRelations || 0 }
    })()

    // v39.6: total = center + incremental (与"中心∪关系"语义一致)
    // 之前 total = filteredRelations.length 只含 relation tree 选中，丢中心范围关系
    // 同时统一 services/objects 等维度也用加法（与关系一致）
    const total = {
      ...(selectedStats.value.total || {}),
      serviceModules: center.serviceModules + (incremental.serviceModules || 0),
      businessObjects: center.businessObjects + (incremental.businessObjects || 0),
      domains: center.domains + (incremental.domains || 0),
      subDomains: center.subDomains + (incremental.subDomains || 0),
      objectRelations: center.objectRelations + incremental.objectRelations
    }

    // v39.6: config = total (口径完全一致, 不再从 selectedStats.total 取)
    const configStats = {
      serviceModules: total.serviceModules,
      businessObjects: total.businessObjects,
      domains: total.domains,
      subDomains: total.subDomains,
      objectRelations: total.objectRelations
    }

    return {
      import: stats.value,
      center,
      external,
      incremental,
      total,
      config: configStats
    }
  })

  // 关系分类树：基于 centerScope 和 previewData.relationships 计算
  const relationCategoryTree = computed(() => {
    if (!previewData.value?.relationships || !previewData.value?.businessObjects) {
      return []
    }

    // v39.5: 去掉 validateData 过滤，与管理页 buildRelationScopeTree 数据源对齐
    // 根因: 图表页用 entityCode (relationCode) 做 filter，会把所有同 code 的关系都过滤掉
    //   → 图表页显示 11 而管理页显示 12 (差 1 条)
    // 修复: 直接用 previewData.relationships 构建 tree，与管理页保持一致
    // 注: validation 错误应通过 UI 提示用户，不应静默过滤掉关系
    return buildRelationCategoryTree(
      previewData.value.relationships,
      centerScope.value,
      previewData.value.businessObjects
    )
  })

  const generateDiagram = () => {
    console.trace('[TRACE-generateDiagram] called, csh=' + (diagramConfig.value?.centerScopeHighlight ?? '?') + ', colorScheme=' + diagramConfig.value?.colorScheme + ', colorGroupBy=' + diagramConfig.value?.colorGroupBy + ', centerScopeColor=' + diagramConfig.value?.centerScopeColor)
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

    // 关键修复 v28: 兜底 - 直接从 filteredRelations (active 关系 ID) 推导 src/tgt BO
    // 防止 relationFilteredBoCodes 因 selectedRelationNodeIds 不含空 code 关系节点而漏掉 TEST600 等
    if (filteredRelations.value && filteredRelations.value.length > 0 && previewData.value?.relationships) {
      const activeRelIds = new Set(filteredRelations.value)
      previewData.value.relationships.forEach(rel => {
        if (activeRelIds.has(rel.id)) {
          finalBoCodes.add(rel.sourceCode)
          finalBoCodes.add(rel.targetCode)
        }
      })
    }

    // [V1.2.9 修复] 移除 [V1.1.13] 跨域兜底
    // 之前: 当上述逻辑都没加入外部 BO 时, 从 previewData 拉所有 cross-boundary 关系
    //   强行引入外部 BO, 完全无视用户没勾选任何关系的情况
    // 现在: 严格按 finalBoCodes (已通过 relationFilteredBoCodes 严格依赖 selectedRelationNodeIds)
    // 取消所有关系勾选时, finalBoCodes = centerScope, 没有任何外部 BO

    const hasFilter = finalBoCodes && finalBoCodes.size > 0

    // [FIX 2026-08-17] 空范围 → 空态: 对象范围 + 关系范围都无选择时 finalBoCodes 为空.
    //   之前 hasFilter=false 会展示 previewData 的全部 BO + 全部关系 (全量大图),
    //   导致 3230 BO / 5721 关系卡死, 且与"空范围=空集"语义矛盾.
    //   现在置空 diagramData 触发渲染层空态提示 ("请先在对象范围选择对象").
    //   注意: 对象范围空但关系范围勾选外部关系时 finalBoCodes 非空 (hasFilter=true),
    //   仍正常展示关系网络, 不受影响. 同时天然覆盖 scopeCode 匹配失败场景 (不再回退全量).
    if (!hasFilter) {
      diagramData.value = null
      // 空态可观测: 与下方 scopeState 同构, 便于确认空范围未走全量渲染
      if (typeof window !== 'undefined') {
        window.__archPage = window.__archPage || {}
        window.__archPage.scopeState = {
          centerScopeBoCount: (centerScope.value || []).length,
          relationBoCount: relationFilteredBoCodes.value?.length || 0,
          finalBoCodesCount: finalBoCodes.size,
          hasFilter,
          scopeMatched: false,
          emptyScope: true,
          filteredBusinessObjects: 0,
          filteredRelationships: 0,
          totalBusinessObjects: previewData.value?.businessObjects?.length || 0
        }
      }
      return null
    }

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

    // 过滤关系：先按范围过滤
    // 关键修复 v28: 用 OR 条件, 只要 src 或 tgt 在 finalBoCodes 中就保留
    // 之前用 AND: TEST600 不在 finalBoCodes 但 BO_WAREHOUSE 在 → id=29 被排除
    // 现象: 图表缺 TEST600 节点和 TEST600→BO_WAREHOUSE 连线
    // v39.5: 去掉 validateData 过滤，与管理页 buildRelationScopeTree 数据源对齐
    //   之前按 entityCode (relationCode) 过滤会误杀所有同 code 的关系 → 图表少 1 条
    let filteredRelationships = hasFilter
      ? previewData.value.relationships.filter(rel =>
          finalBoCodes.has(rel.sourceCode) || finalBoCodes.has(rel.targetCode)
        )
      : previewData.value.relationships

    // 根据关系范围选择过滤关系
    // 关键修复 v26: filteredRelations 现在是 relationId[] (按 id 去重) 而非 code[]
    // 用 rel.id 匹配, 正确保留空 code 关系 (id=29 TEST600↔BO_WAREHOUSE)
    const selectedRelationIds = filteredRelations.value
    if (hasFilter) {
      if (selectedRelationIds && selectedRelationIds.length > 0) {
        filteredRelationships = filteredRelationships.filter(rel => selectedRelationIds.includes(rel.id))
      } else {
        // [FIX 2026-08-13 v2] 未选择任何关系时, 不展示任何关系连线 (连内部关系也不展示).
        //   之前此处保留"源靶都在对象范围"的内部关系, 导致折叠到子领域后子领域之间仍有连线,
        //   与用户预期不符 (用户反馈: 没选关系范围却"多展示"了所有内部关系).
        //   语义: 没选关系 = 只渲染对象范围节点, 0 条关系连线.
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
          code: domain.code || domain.name,
          isCenter: domainData ? domainData.center === domainData.total && domainData.total > 0 : false,
          modules: []
        }
        domain.modules?.forEach(subDomain => {
          const sdData = subDomainSmCenterMap.get(subDomain.name)
          const filteredSubDomain = {
            name: subDomain.name,
            code: subDomain.code || subDomain.name,
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

    // v31: 补齐范围外 SM 的层级 (domain/subDomain/serviceModule)
    //      如果 SM 在 filteredSmCodes 但其层级不在 formal domainProducts 中，
    //      为其创建 synthetic hierarchy entries → 确保 SM 图表有容器
    if (hasFilter) {
      const placedSmCodes = new Set()
      filteredDomainProducts.forEach(domain => {
        domain.modules?.forEach(sd => {
          sd.submodules?.forEach(sm => {
            placedSmCodes.add(sm.code)
          })
        })
      })

      // 收集未放置的 orphan SM
      filteredSmCodes.forEach(smCode => {
        if (!placedSmCodes.has(smCode)) {
          // 从 businessObjects 找到 SM 的层级信息
          const smBos = filteredBusinessObjects.filter(bo => bo.serviceModule === smCode)
          if (smBos.length > 0) {
            const domainName = smBos[0].domain || '其他领域'
            const subDomainName = smBos[0].subDomain || '其他子领域'
            const smName = smBos[0].serviceModuleName || smCode

            // 查找或创建 domain
            let domainEntry = filteredDomainProducts.find(d => d.name === domainName)
            if (!domainEntry) {
              domainEntry = {
                name: domainName,
                code: domainName,
                isCenter: false,
                modules: []
              }
              filteredDomainProducts.push(domainEntry)
            }

            // 查找或创建 subDomain
            let sdEntry = domainEntry.modules.find(sd => sd.name === subDomainName)
            if (!sdEntry) {
              sdEntry = {
                name: subDomainName,
                code: subDomainName,
                isCenter: false,
                submodules: []
              }
              domainEntry.modules.push(sdEntry)
            }

            // 添加 orphan SM
            sdEntry.submodules.push({
              code: smCode,
              name: smName,
              isCenter: false,
              businessObjects: smBos.map(bo => typeof bo === 'string' ? bo : (bo.code || bo.name))
            })
          }
        }
      })
    }

    // [PERF 2026-08-13] 领域数量变化 → 数据范围结构变了 (关系范围引入了新领域/子领域),
    //   重置展开层级状态, 让渲染层按自适应默认展开重新计算初始层级.
    //   根因: 对象范围 1 个领域 + 选"跨领域关系"引入外部领域后, 若沿用用户之前的
    //   expandLevelUserSet/groupManualSet (如"展开到业务对象"), 图表仍停留在业务对象级别,
    //   而非自适应到"展开到领域(多个领域)". 领域数变化即触发重置.
    const currentDomainCount = filteredDomainProducts.length
    if (currentDomainCount !== lastFilteredDomainCount.value) {
      // [LOG 2026-08-13] 关键日志: 领域数变化 → 触发状态重置 (展开层级 + 默认颜色配置).
      console.log('[generateDiagram] 领域数变化: ' + lastFilteredDomainCount.value + ' → ' + currentDomainCount +
        ' | 关系数=' + filteredRelationships.length +
        ' | 中心BO=' + (centerScope.value || []).length +
        ' | 最终BO=' + finalBoCodes.size)

      lastFilteredDomainCount.value = currentDomainCount
      configStore.resetExpandState()

      // [DEFAULT-COLOR 2026-08-13] 数据范围结构变化 → 重置默认颜色配置:
      //   1) colorGroupBy 跟随初始展开层级规则 (领域>1→domain, 子领域>1→subDomain, 否则 serviceModule)
      //   2) centerScopeHighlight 无外部 BO (只对象范围) 时 false, 有外部 BO 时 true.
      //      用户诉求: 没选关系范围时, 不区分对象范围(=false), 颜色按初始展开层级分组.
      const subDomainCount = filteredDomainProducts.reduce((n, d) => n + (d.modules?.length || 0), 0)
      const defaultGroupBy = currentDomainCount > 1
        ? 'domain'
        : subDomainCount > 1
          ? 'subDomain'
          : 'serviceModule'
      const hasExternalBo = finalBoCodes.size > (centerScope.value || []).length
      configStore.applyDefaultColorConfig(defaultGroupBy, hasExternalBo)
    }

    // [OBS 2026-08-08] 对象范围链路可观测摘要:
    //   scopeCode → finalBoCodes → 过滤后各层计数. 快速确认范围过滤是否符合预期
    //   (如 SCP 只含供应链计划 BO, 而非全量 3230). 用法: window.__archPage.scopeState.
    //   scopeMatched=false(有过滤但 finalBoCodes 为空) 即命中"scopeCode 匹配失败",
    //   应中止而非静默回退全量 (见项目铁律).
    if (typeof window !== 'undefined') {
      window.__archPage = window.__archPage || {}
      window.__archPage.scopeState = {
        centerScopeBoCount: (centerScope.value || []).length,
        relationBoCount: relationFilteredBoCodes.value?.length || 0,
        finalBoCodesCount: finalBoCodes.size,
        hasFilter,
        scopeMatched: hasFilter ? finalBoCodes.size > 0 : null,
        filteredDomains: filteredDomainProducts.length,
        filteredSubDomains: filteredDomainProducts.reduce((n, d) => n + (d.modules?.length || 0), 0),
        filteredServiceModules: filteredServiceModules.length,
        filteredBusinessObjects: filteredBusinessObjects.length,
        filteredRelationships: filteredRelationships.length,
        totalBusinessObjects: previewData.value?.businessObjects?.length || 0
      }
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

        // [FIX 2026-08-02] 统一管道入口 (spec 4.2.1): preview 裁剪到当前 scope
        // (filteredDomainProducts 已按 finalBoCodes 过滤), relationships 同步裁剪,
        // 保持与旧路径一致的过滤语义; 无过滤时用全量 preview
        const pipelinePreview = {
          domainProducts: filteredDomainProducts,
          relationships: hasFilter
            ? (previewData.value?.relationships || []).filter(rel =>
                finalBoCodes.has(rel.sourceCode) && finalBoCodes.has(rel.targetCode))
            : (previewData.value?.relationships || [])
        }

        diagramData.value = buildServiceModuleDiagramData({
          preview: pipelinePreview,
          chartType: 'serviceModule',
          versionId: currentVersionId.value,
          // [FIX 2026-08-02] L1 树缓存 key 必须是"树的输入指纹" (preview 本身):
          //   之前用 computeConfigHash (含颜色/布局配置) → 切配色/颜色分组时 L1 树重建,
          //   违反 spec 4.4 (颜色变化只触发 L3/L4)。preview 指纹由内容决定,
          //   天然区分 BO/SM (relationships 不同) 且不受颜色/布局配置影响。
          scopeHash: JSON.stringify(pipelinePreview),
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

        // [DEFAULT-LEVEL 2026-08-12] 初始展开层级不再在此套用范围折叠:
        // 由渲染层 EmbeddedChartView 按分组数量自适应 (applyDefaultExpandByCount) 决定,
        // 并在 sharedApplyGroupStates/applyDefaultExpandByCount 阶段就地应用到渲染树.

        // 5. 使用 buildDiagramData，复用所有渲染逻辑
        // [Task 10 2026-08-02] 统一管道入口 (spec 4.2.1): preview 裁剪到当前 scope
        //   (filteredDomainProducts 已按 finalBoCodes 过滤), relationships 用 finalRelationships
        //   (保留 selectedRelationIds 关系选择 + internalRelationFilter 过滤语义),
        //   投影阶段会把指向范围外 BO 的悬空边丢弃, 与旧语法层 filter 行为一致。
        //   chartType=businessObject → diagramDataBuilder 内部走 L1树→L2投影→L3着色 管道。
        const pipelinePreview = {
          domainProducts: filteredDomainProducts,
          relationships: finalRelationships || []
        }
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
          centerScopeHighlight: diagramConfig.value.centerScopeHighlight,
          preview: pipelinePreview,
          chartType: 'businessObject',
          versionId: currentVersionId.value,
          // [FIX 2026-08-02] L1 树缓存 key 用 preview 输入指纹 (同 SM 路径):
          //   computeConfigHash 含颜色/布局配置, 切配色/颜色分组时会让 L1 树重建,
          //   违反 spec 4.4 (颜色变化只触发 L3/L4)。preview 指纹不受颜色配置影响。
          scopeHash: JSON.stringify(pipelinePreview)
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
            // [v39 关系线标题修复] 优先 rel.code (关系实例编码), fallback 到 rel.relationCode (关系类型编码)
            // 之前用 rel.relationDesc (描述) - 用户看到的不是关系编码
            label: rel.code || rel.relationCode || '',
            relationCode: rel.relationCode,
            annotationCategory: rel.annotationCategory || 'info',
            annotationContent: rel.annotationContent || '',
            // [v40 修复] 之前 unifiedLinks 缺失 relationType / relationDirection
            //   UnifiedRenderer 渲染时拿不到 '双向' → 全部回退为 -->
            //   tooltip 也显示不了 enum 名称
            relationType: rel.relationType || '',
            relationDirection: rel.relationDirection || null,
            // 关系实例编码 (透传给 UnifiedRenderer 用)
            code: rel.code || '',
            relationDesc: rel.relationDesc || ''
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

    // [2026-06-15] 写入 diagramData 缓存
    //  - 切 tab 回来时直接命中, 不重新生成
    //  - 范围/配置变了 → configHash 不匹配 → 自动失效
    try {
      const hash = computeConfigHash()
      chartArchStore.setDiagramCache(diagramData.value, hash)
    } catch (e) {
      console.warn('[useDiagramData] Failed to cache diagramData:', e)
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
        overallDirection: 'TB',
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
    // [V1.2.9 修复] 用户在图表页手动切换时, 让 archRelationIdsRef 失效
    //   这样 filteredRelations 回退到 getSelectedRelationIds (按当前 selectedRelationNodeIds 算)
    archRelationIdsRef.value = null
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
    // [V1.2.9 修复] 用户在图表页清空关系范围时, 让 archRelationIdsRef 失效
    archRelationIdsRef.value = null
    selectedRelationNodeIds.value = []
  }

  // [E2 2026-08-02] 合并配置字段 watch → 单个组合 watch:
  //   之前 customColors/colorScheme/colorGroupBy/centerScopeHighlight/centerScopeColor
  //   各有独立 watch, 用户在同一 flush 内快速切换多个配置时 (如连续选配色+分组维度),
  //   每次字段变化都触发一次完整 generateDiagram (同步全量重建)。
  //   合并后同一 flush 内多次字段变化只生成一次, 使用最终值, 消除中间态的浪费渲染。
  //   [FIX 2026-08-09] centerScopeHighlight 从本 watch 移除: 它只影响颜色, 不改变结构。
  //     若在此触发 generateDiagram → 全量重建 → GroupModel.fromUserConfig 不保留用户
  //     手动折叠/展开状态 → 切换"区分/不区分业务对象"后已展开的分组被折叠。
  //     改为下方单独 watch 浅更新 diagramData.centerScopeHighlight, 由 MermaidComponent
  //     的 updateColorsOnly 增量变色处理 (节点/连线/图例颜色更新, 不重建结构)。
  watch(
    () => {
      const cfg = diagramConfig.value || {}
      const cc = cfg.customColors
      return [
        cfg.colorScheme,
        cfg.colorGroupBy,
        // cfg.centerScopeHighlight,  // 已移除, 见下方单独 watch
        cfg.centerScopeColor,
        cc ? JSON.stringify(cc) : ''
      ].join('|')
    },
    (newStr, oldStr) => {
      if (newStr !== oldStr && previewData.value) {
        generateDiagram()
      }
    }
  )

  // [FIX 2026-08-09] 区分/不区分业务对象 (centerScopeHighlight) 只影响颜色 → 浅更新
  //   diagramData.centerScopeHighlight, 不触发 generateDiagram 全量重建 (否则丢失
  //   用户手动折叠/展开状态, 见上方注释). MermaidComponent 检测到 centerScopeHighlight
  //   变化且 nodes/links 未变 → 走 updateColorsOnly 增量变色路径.
  // [FIX 2026-08-09 v2] 必须"原地修改"而非新建对象引用!
  //   之前 `diagramData.value = {...diagramData.value, centerScopeHighlight}` 产生新引用,
  //   EmbeddedChartView.layoutControlConfig computed 依赖 diagramData.value → 重新求值
  //   → 返回新 groups 对象 → MermaidComponent 的 layoutControlConfig watch 判 sig 变化
  //   → 走全量 renderMermaid() → 用户手动展开的分组(如采购供应)被重新折叠.
  //   现改为原地赋值: diagramData.value 引用不变, layoutControlConfig computed 不重算,
  //   仅 MermaidComponent 对 props.diagramData 的 deep watch 捕获 centerScopeHighlight
  //   变化 → nodes/links 未变 → updateColorsOnly 增量变色. (浏览器实测确认)
  watch(
    () => diagramConfig.value?.centerScopeHighlight,
    (newVal, oldVal) => {
      if (newVal !== oldVal && diagramData.value) {
        diagramData.value.centerScopeHighlight = newVal
        // [FIX 2026-08-15] 同步刷新 nodes 的 isCenter 字段 (原实现只改 highlight 不重算 isCenter):
        //   colorize 在 generateDiagram 时把 isCenter 烘焙进节点; 增量切"区分/不区分对象范围"时
        //   nodes 的 isCenter 停留旧值 → 图例 hasCenterNodes/整组跳过判定读到陈旧 false →
        //   legend 不出现"对象范围"项. 这里按新 highlight + centerScope 原地重算 isCenter,
        //   使图例/增量变色/整组跳过逻辑一致. (与 colorize L58 的 isCenter 口径一致)
        const centerSet = new Set(centerScope.value || [])
        ;(diagramData.value.nodes || []).forEach(n => {
          n.isCenter = !!newVal && centerSet.has(n.code)
        })
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

  // [SIMPLE 2026-08-15] 关系连线关联点 (hideLinkLabelTails) 原地更新 diagramData:
  //   之前无此 watch — 切换关联点只改 store, 不触发 generateDiagram, diagramData.hideLinkLabelTails
  //   停留旧值 → MermaidComponent 的 shouldHideTails 读到陈旧值 → "直线 + 手动打开关联点"也看不到拖尾线.
  //   现原地更新 (引用不变), MermaidComponent deep watch 捕获 → nodes/links 未变 → renderMermaid 重绘,
  //   processSvg 用新值重新判定拖尾线显隐. (与 centerScopeHighlight 原地更新同一模式)
  watch(
    () => diagramConfig.value?.hideLinkLabelTails,
    (newVal, oldVal) => {
      if (newVal !== oldVal && diagramData.value) {
        diagramData.value.hideLinkLabelTails = newVal
      }
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

  // [2026-06-15] 计算配置/范围 hash
  //  包含所有会进入 buildDiagramData / buildServiceModuleDiagramData 的字段
  //  任何一个变了, 缓存就失效, 触发重新生成
  //  - 用户改 colorScheme / nodeTextColor / centerScope 等 → 立即生效 (下次 generate)
  //  - 切 tab 回来时 → hash 不匹配 → 不读缓存, 走 generate
  const computeConfigHash = () => {
    const cfg = configStore
    // 选所有影响图表输出的字段 (不包含 timestamp / id / 调试字段)
    const payload = {
      // 1) 范围 (影响 filtered*)
      chartType: cfg.chartType,
      centerScope: [...(cfg.centerScope || [])].sort(),
      selectedRelationNodeIds: [...(cfg.selectedRelationNodeIds || [])].sort(),
      relationFilteredBoCodes: [...(cfg.relationFilteredBoCodes || [])].sort(),

      // 2) 配色
      colorGroupBy: cfg.colorGroupBy,
      colorScheme: cfg.colorScheme,
      nodeTextColor: cfg.nodeTextColor,
      centerScopeColor: cfg.centerScopeColor,
      centerDomain: cfg.centerDomain,
      centerDomainColor: cfg.centerDomainColor,
      centerScopeHighlight: cfg.centerScopeHighlight,
      customColors: cfg.customColors,

      // 3) 布局
      layoutTemplate: cfg.layoutTemplate,
      layoutEngine: cfg.layoutEngine,
      layoutControlConfig: cfg.layoutControlConfig,
      positions: cfg.positions,
      preserveModelOrder: cfg.preserveModelOrder,
      hideLinkLabelTails: cfg.hideLinkLabelTails,
      useLegacyGroupControl: cfg.useLegacyGroupControl,

      // 4) 注解
      annotationPanelPosition: cfg.annotationPanelPosition,
      showAnnotationIcons: cfg.showAnnotationIcons,
      assignmentMode: cfg.assignmentMode
    }
    // 用 JSON.stringify 作 hash (简单够用; 不需要 crypto 防碰撞)
    return JSON.stringify(payload)
  }

  // [2026-06-15] 尝试从 Pinia 缓存读 diagramData
  //  命中场景:
  //   - 切 tab 回来 (用户已 generate 过, archData/configStore 没变)
  //  未命中场景:
  //   - 首次进入 / F5 后 (Pinia 状态丢失)
  //   - 范围/配置变了 (configHash 不匹配)
  //   - 超过 30 分钟 TTL
  //   - 缓存版本不匹配 (schema 升级)
  //  @returns 命中返回 data, 未命中返回 null
  const loadCachedDiagram = () => {
    try {
      const hash = computeConfigHash()
      const cached = chartArchStore.getDiagramCache(hash)
      if (cached) {
        diagramData.value = cached
        return cached
      }
      return null
    } catch (e) {
      console.warn('[useDiagramData] Failed to load cached diagram:', e)
      return null
    }
  }

  const resetData = () => {
    clearData()
    centerScope.value = []
    relationFilteredBoCodes.value = null
    internalRelationFilter.value = 'off'
    diagramData.value = null
    lastFilteredDomainCount.value = 0
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
    const { versionId, hierarchyFilter, relationTypeFilter, relationIds: archRelationIds, relationCategoryTypes } = archData

    // [FIX 2026-08-02] 记录当前版本 ID (统一管道 L1 树缓存 key 组成部分)
    currentVersionId.value = versionId || 0

    loading.value = true
    try {
      const result = await buildPreviewDataFromArchData(null, versionId, hierarchyFilter)
      
      previewData.value = {
        domainProducts: result.allDomainProducts || result.domainProducts,
        businessObjects: result.allBusinessObjects || result.businessObjects,
        serviceModules: result.allServiceModules || result.serviceModules,
        relationships: result.relationships
      }

      // [PERF 2026-08-13] 保存基础 previewData 快照, 供关系范围变更时轻量恢复
      //   (跳过 architecture/preview 重拉 + 清理上次补全累积的外部 BO)。
      basePreviewData.value = JSON.parse(JSON.stringify(previewData.value))

      // 直接使用 buildPreviewDataFromArchData 返回的 centerScope，避免重复 API 调用
      const centerScopeCodes = result.centerScope || []
      // [FIX 2026-08-17] 空对象范围 → 后端 architecture/preview 无 filter 时把 center_scope
      //   设为全部 BO (TTTTT000/V11 为 3230), 导致空范围图表仍渲染全量大图.
      //   这里空范围强制 centerScope = [] (空集), 与"空范围=空集"语义一致:
      //   - 关系范围也空 → finalBoCodes 空 → generateDiagram 空态 (不渲染全量, 见下方空态分支)
      //   - 关系范围勾选 → finalBoCodes = 关系引入BO → 正常展示关系网络
      //   有对象范围时仍采用后端返回的 centerScope (按 filter 过滤, 正确).
      const hasObjectScope = hierarchyFilter && Object.keys(hierarchyFilter).length > 0
      configStore.updateCenterScope(hasObjectScope ? centerScopeCodes : [])

      isInitializedFromArchData.value = true
      
      updateCenterScopeMarkers()
      
      rawData.value = {
        businessObjectData: previewData.value.businessObjects || [],
        serviceComponentData: previewData.value.serviceModules || [],
        relationshipData: previewData.value.relationships || []
      }
      
      await nextTick()
      
      await applyRelationScope(archRelationIds, relationTypeFilter, versionId)

      loading.value = false
    } catch (error) {
      console.error('[useDiagramData] Failed to initialize from arch data:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 应用关系范围: 更新 archRelationIdsRef + 反向匹配 selectedRelationNodeIds + 补全缺失 BO。
   * [PERF 2026-08-13] 抽取自 initFromArchDataManager, 供"关系范围变更"轻量刷新复用
   *   (跳过 architecture/preview 重拉)。centerScopeCodes 改为 centerScope.value (对象范围不变)。
   */
  async function applyRelationScope(archRelationIds, relationTypeFilter, versionId) {
    // [V1.2.9] 把精确的关系 IDs 存到 ref, 让 filteredRelations 优先用这个 (避免反向匹配过度匹配)
    if (archRelationIds && archRelationIds.length > 0) {
      archRelationIdsRef.value = [...archRelationIds]
    } else {
      archRelationIdsRef.value = null
    }

    if (relationTypeFilter && relationTypeFilter.length > 0) {
      selectedRelationNodeIds.value = convertToRelationNodeIds(relationTypeFilter)
    }

    // 节点匹配优先级:
    //   1. archRelationIds 反向匹配（精确）
    //   2. relationTypeFilter 匹配（回退）
    //   3. 未选关系 → 空 (图表只渲染对象范围)
    const archRelationIdsSet = archRelationIds && archRelationIds.length > 0
      ? new Set(archRelationIds)
      : null

    if (archRelationIdsSet && relationCategoryTree.value) {
      const matchedLeafNodes = []
      function findLeafNodesWithRelationIds(node, ancestors) {
        const hasChildren = node.children && node.children.length > 0
        if (!hasChildren && node.relationIds && node.relationIds.length > 0) {
          const hasIntersection = node.relationIds.some(id => archRelationIdsSet.has(id))
          if (hasIntersection) {
            matchedLeafNodes.push({ node, ancestors: [...ancestors] })
          }
        }
        if (hasChildren) {
          node.children.forEach(child => findLeafNodesWithRelationIds(child, [...ancestors, node]))
        }
      }
      relationCategoryTree.value.forEach(rootNode => findLeafNodesWithRelationIds(rootNode, []))

      const selectedIdSet = new Set()
      matchedLeafNodes.forEach(({ node, ancestors }) => {
        selectedIdSet.add(node.id)
        ancestors.forEach(ancestor => selectedIdSet.add(ancestor.id))
      })

      if (selectedIdSet.size > 0) {
        selectedRelationNodeIds.value = Array.from(selectedIdSet)
      }
    } else if (relationTypeFilter && relationTypeFilter.length > 0) {
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
      selectedRelationNodeIds.value = []
    }

    if (selectedRelationNodeIds.value && selectedRelationNodeIds.value.length > 0) {
      // 改用 getSelectedRelationIds (按 rel.id 去重) 收集选中关系
      const relationIds = new Set(getSelectedRelationIds(relationCategoryTree.value, selectedRelationNodeIds.value))

      const filteredCodes = new Set(centerScope.value || [])

      if (previewData.value.relationships) {
        previewData.value.relationships.forEach(rel => {
          if (relationIds.has(rel.id)) {
            filteredCodes.add(rel.sourceCode)
            filteredCodes.add(rel.targetCode)
          }
        })
      }

      // 补全"中心范围外、但有选中关系涉及"的 BO (否则图表节点缺失)
      const existingBoCodes = new Set((previewData.value.businessObjects || []).map(b => b.code))
      const missingBoCodes = Array.from(filteredCodes).filter(c => !existingBoCodes.has(c))
      if (missingBoCodes.length > 0) {
        try {
          const missingRes = await apiV2.get(`/bo/business_object?version_id=${versionId}&codes=${missingBoCodes.join(',')}`)
          if (missingRes.success && missingRes.data?.items) {
            const converted = missingRes.data.items.map(bo => ({
              id: bo.id,
              code: bo.code,
              name: bo.name,
              domainId: bo.domain_id,
              domain: bo.domain_name,
              subDomainId: bo.sub_domain_id,
              subDomain: bo.sub_domain_name,
              serviceModuleId: bo.service_module_id,
              serviceModule: bo.service_module_name,
              serviceModuleName: bo.service_module_name
            }))

            const synthDomainMap = new Map()
            converted.forEach(bo => {
              const dn = bo.domain || '未分类领域'
              const sdn = bo.subDomain || '未分类子域'
              const smn = bo.serviceModule || bo.serviceModuleName || '未分类服务模块'
              if (!synthDomainMap.has(dn)) synthDomainMap.set(dn, new Map())
              const sdMap = synthDomainMap.get(dn)
              if (!sdMap.has(sdn)) sdMap.set(sdn, new Map())
              const smMap = sdMap.get(sdn)
              if (!smMap.has(smn)) smMap.set(smn, { id: bo.serviceModuleId, code: smn, name: smn, businessObjects: [] })
              smMap.get(smn).businessObjects.push(bo.code)
            })

            const existingDomains = previewData.value.domainProducts || []
            const extraDomainProducts = []
            synthDomainMap.forEach((sdMap, dn) => {
              const existing = existingDomains.find(d => d.name === dn)
              if (existing) {
                if (!existing.modules) existing.modules = []
                sdMap.forEach((smMap, sdn) => {
                  let subDomainGroup = existing.modules.find(m => m.name === sdn)
                  if (!subDomainGroup) {
                    subDomainGroup = { name: sdn, submodules: [] }
                    existing.modules.push(subDomainGroup)
                  }
                  if (!subDomainGroup.submodules) subDomainGroup.submodules = []
                  smMap.forEach(sm => {
                    let smGroup = subDomainGroup.submodules.find(s => s.code === sm.code)
                    if (!smGroup) {
                      smGroup = { id: sm.id, code: sm.code, name: sm.name, businessObjects: [] }
                      subDomainGroup.submodules.push(smGroup)
                    }
                    sm.businessObjects.forEach(boCode => {
                      if (!smGroup.businessObjects.includes(boCode)) smGroup.businessObjects.push(boCode)
                    })
                  })
                })
              } else {
                const modules = []
                sdMap.forEach((smMap, sdn) => {
                  const submodules = []
                  smMap.forEach(sm => submodules.push(sm))
                  modules.push({ name: sdn, submodules })
                })
                extraDomainProducts.push({ name: dn, modules })
              }
            })

            previewData.value = {
              ...previewData.value,
              businessObjects: [...(previewData.value.businessObjects || []), ...converted],
              domainProducts: [...(previewData.value.domainProducts || []), ...extraDomainProducts]
            }
            console.log(`[applyRelationScope] 补全 ${converted.length} 个缺失 BO, ${extraDomainProducts.length} 个缺失 domain`)
          }
        } catch (err) {
          console.warn('[applyRelationScope] 补全缺失 BO 失败:', err.message)
        }
      }
    }
  }

  /**
   * 关系范围变更的轻量刷新 (对象范围不变):
   *   1. 从 basePreviewData 快照恢复 previewData (清理上次补全累积的外部 BO)
   *   2. 重新应用关系范围 (反向匹配 + 补全)
   * 相比 initFromArchDataManager, 跳过 architecture/preview API 重拉。
   */
  async function updateRelationScope(archData) {
    const { relationTypeFilter, relationIds: archRelationIds, versionId } = archData

    if (basePreviewData.value) {
      previewData.value = JSON.parse(JSON.stringify(basePreviewData.value))
    }

    await applyRelationScope(archRelationIds, relationTypeFilter, versionId || currentVersionId.value)
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
    initFromArchDataManager,
    updateRelationScope,

    // [2026-06-15] 缓存读写 (切 tab 状态恢复用)
    loadCachedDiagram,
    computeConfigHash
  }
}
