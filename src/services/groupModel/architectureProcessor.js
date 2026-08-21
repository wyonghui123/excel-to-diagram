/**
 * 架构元素处理器
 * 
 * 从架构元素数据（领域、子领域、服务模块、业务对象）构建统一分组模型
 * 
 * 数据流：
 * 架构元素数据 → buildGroupModelFromArchitecture → Group[] 分组模型
 */

import { 
  GroupType, 
  createGroup, 
  findGroupByElementCode 
} from './types.js'
import { ChartType, getChartTypeConfig } from './chartTypeConfig.js'

/**
 * 从架构元素数据构建统一分组模型
 * 
 * @param {Object} architectureData - 架构元素数据
 * @param {Array} architectureData.domainProducts - 领域产品数据
 * @param {Array} architectureData.businessObjects - 业务对象数据
 * @param {Array} architectureData.serviceModules - 服务模块数据
 * @param {string} chartType - 图表类型 ('businessObject' | 'serviceModule')
 * @returns {Array} 分组模型数组
 */
export function buildGroupModelFromArchitecture(architectureData, chartType) {
  const { domainProducts, businessObjects, serviceModules } = architectureData

  if (chartType === ChartType.SERVICE_MODULE) {
    return buildServiceModuleGroupModel(domainProducts, serviceModules)
  }

  return buildBusinessObjectGroupModel(domainProducts, businessObjects)
}

/**
 * 构建业务对象图的分组模型
 * 层级结构：领域 → 子领域 → 服务模块 → 业务对象
 */
function buildBusinessObjectGroupModel(domainProducts, businessObjects) {
  if (!domainProducts || domainProducts.length === 0) {
    return []
  }

  const boMap = new Map()
  if (businessObjects) {
    businessObjects.forEach(bo => {
      if (bo.code) {
        boMap.set(bo.code, bo)
      }
    })
  }

  const rootGroups = []

  domainProducts.forEach(domain => {
    const domainGroup = createGroup({
      type: GroupType.DOMAIN,
      title: domain.name,
      isCenter: domain.isCenter || false,
      elementRef: {
        type: GroupType.DOMAIN,
        code: domain.code || domain.name,
        name: domain.name
      }
    })

    if (domain.modules && domain.modules.length > 0) {
      domain.modules.forEach(subDomain => {
        const subDomainGroup = createGroup({
          type: GroupType.SUB_DOMAIN,
          title: subDomain.name,
          isCenter: subDomain.isCenter || false,
          parentId: domainGroup.id,
          elementRef: {
            type: GroupType.SUB_DOMAIN,
            code: subDomain.code || subDomain.name,
            name: subDomain.name,
            parentCode: domain.code || domain.name
          }
        })

        if (subDomain.submodules && subDomain.submodules.length > 0) {
          subDomain.submodules.forEach(sm => {
            const smGroup = createGroup({
              type: GroupType.SERVICE_MODULE,
              title: sm.name,
              isCenter: sm.isCenter || false,
              parentId: subDomainGroup.id,
              elementRef: {
                type: GroupType.SERVICE_MODULE,
                code: sm.code || sm.name,
                name: sm.name,
                parentCode: subDomain.code || subDomain.name,
                grandparentCode: domain.code || domain.name
              }
            })

            if (sm.businessObjects && sm.businessObjects.length > 0) {
              sm.businessObjects.forEach(bo => {
                const boData = typeof bo === 'string'
                  ? boMap.get(bo) || { code: bo, name: bo }
                  : bo

                const boGroup = createGroup({
                  type: GroupType.BUSINESS_OBJECT,
                  title: boData.name || boData.code || bo,
                  isCenter: boData.isCenter || false,
                  parentId: smGroup.id,
                  elementRef: {
                    type: GroupType.BUSINESS_OBJECT,
                    code: boData.code || boData.name || bo,
                    name: boData.name || boData.code || bo,
                    parentCode: sm.code || sm.name
                  }
                })
                smGroup.children.push(boGroup)
              })
            }

            if (smGroup.children.length > 0) {
              subDomainGroup.children.push(smGroup)
            }
          })
        }

        if (subDomainGroup.children.length > 0) {
          domainGroup.children.push(subDomainGroup)
        }
      })
    }

    if (domainGroup.children.length > 0) {
      rootGroups.push(domainGroup)
    }
  })

  return rootGroups
}

/**
 * 构建服务模块图的分组模型
 * 层级结构：领域 → 子领域 → 服务模块（末端节点）
 */
function buildServiceModuleGroupModel(domainProducts, serviceModules) {
  if (!domainProducts || domainProducts.length === 0) {
    return []
  }

  const smMap = new Map()
  if (serviceModules) {
    serviceModules.forEach(sm => {
      if (sm.code) {
        smMap.set(sm.code, sm)
      }
    })
  }

  const rootGroups = []

  domainProducts.forEach(domain => {
    const domainGroup = createGroup({
      type: GroupType.DOMAIN,
      title: domain.name,
      elementRef: {
        type: GroupType.DOMAIN,
        code: domain.code || domain.name,
        name: domain.name
      }
    })

    if (domain.modules && domain.modules.length > 0) {
      domain.modules.forEach(subDomain => {
        const subDomainGroup = createGroup({
          type: GroupType.SUB_DOMAIN,
          title: subDomain.name,
          parentId: domainGroup.id,
          elementRef: {
            type: GroupType.SUB_DOMAIN,
            code: subDomain.code || subDomain.name,
            name: subDomain.name,
            parentCode: domain.code || domain.name
          }
        })

        if (subDomain.submodules && subDomain.submodules.length > 0) {
          subDomain.submodules.forEach(sm => {
            const smData = smMap.get(sm.code)
            const smGroup = createGroup({
              type: GroupType.SERVICE_MODULE,
              title: smData?.name || smData?.code || sm.name,
              parentId: subDomainGroup.id,
              elementRef: {
                type: GroupType.SERVICE_MODULE,
                code: smData?.code || sm.code,
                name: smData?.name || sm.name,
                parentCode: subDomain.code || subDomain.name
              }
            })
            subDomainGroup.containers.push(smGroup)
          })
        }

        if (subDomainGroup.containers.length > 0) {
          domainGroup.children.push(subDomainGroup)
        }
      })
    }

    if (domainGroup.children.length > 0) {
      rootGroups.push(domainGroup)
    }
  })

  return rootGroups
}

/**
 * 从分组模型中提取所有末端节点
 */
export function extractTerminalGroups(groups, chartType) {
  const config = getChartTypeConfig(chartType)
  const terminals = []

  function traverse(groupList) {
    groupList.forEach(group => {
      if (config.terminalTypes.includes(group.type)) {
        terminals.push(group)
      }
      if (group.children && group.children.length > 0) {
        traverse(group.children)
      }
      // 处理 containers（终端节点）
      if (group.containers && group.containers.length > 0) {
        group.containers.forEach(container => {
          if (config.terminalTypes.includes(container.type)) {
            terminals.push(container)
          }
        })
      }
    })
  }

  traverse(groups)
  return terminals
}

/**
 * 构建节点ID映射
 * 用于将业务对象编码/名称映射到分组ID
 */
export function buildNodeIdMap(groups, chartType) {
  const terminals = extractTerminalGroups(groups, chartType)
  const codeToIdMap = new Map()
  const nameToIdMap = new Map()
  const idToCodeMap = new Map()

  terminals.forEach(group => {
    if (group.elementRef) {
      if (group.elementRef.code) {
        codeToIdMap.set(group.elementRef.code, group.id)
      }
      if (group.elementRef.name) {
        nameToIdMap.set(group.elementRef.name, group.id)
      }
      idToCodeMap.set(group.id, group.elementRef.code || group.elementRef.name)
    }
  })

  return {
    codeToIdMap,
    nameToIdMap,
    idToCodeMap
  }
}

/**
 * 过滤分组模型（基于选中的业务对象编码）
 */
export function filterGroupModelByScope(groups, selectedCodes, chartType) {
  if (!selectedCodes || selectedCodes.size === 0) {
    return groups
  }

  const config = getChartTypeConfig(chartType)

  function filterGroup(group, depth = 0) {
    if (config.terminalTypes.includes(group.type)) {
      const code = group.elementRef?.code
      const isInScope = selectedCodes.has(code)
      return isInScope ? { ...group, children: [] } : null
    }

    const filteredChildren = group.children
      .map(child => filterGroup(child, depth + 1))
      .filter(Boolean)
    
    if (filteredChildren.length === 0) {
      return null
    }

    return {
      ...group,
      isCenter: group.isCenter,
      children: filteredChildren
    }
  }

  const result = groups.map(filterGroup).filter(Boolean)
  return result
}

/**
 * 从扁平结构构建分组模型
 *
 * 契约见 chart-data-flow-and-interaction-upgrade.md §5.10.2 ①
 *
 * @param {Object} flattenData - 扁平结构 { domains, subDomains, serviceModules, businessObjects, ... }
 * @param {string} chartType - 'businessObject' | 'serviceModule'
 * @returns {Array} Group[] - 顶层 Group (DOMAIN)
 */
export function buildGroupsFromFlatten(flattenData, chartType) {
  if (!flattenData || !chartType) return []

  const { domains = [], subDomains = [], serviceModules = [], businessObjects = [] } = flattenData

  // 过滤有效数据
  if (!Array.isArray(domains) || !Array.isArray(businessObjects)) return []

  const businessObjectChart = chartType === ChartType.BUSINESS_OBJECT

  // 构建索引 (按 code 去重)
  const domainByCode = new Map()
  const subDomainByCode = new Map()
  const serviceModuleByCode = new Map()
  const boByCode = new Map()

  domains.forEach(d => { if (d?.code) domainByCode.set(d.code, d) })
  subDomains.forEach(sd => { if (sd?.code && !subDomainByCode.has(sd.code)) subDomainByCode.set(sd.code, sd) })
  serviceModules.forEach(sm => { if (sm?.code && !serviceModuleByCode.has(sm.code)) serviceModuleByCode.set(sm.code, sm) })
  businessObjects.forEach(bo => { if (bo?.code && !boByCode.has(bo.code)) boByCode.set(bo.code, bo) })

  // 决定 sub_domain_id / domain_id 关联键（flattenData 用 id，previewData 用 code）
  // 同时构建 sd→domain 映射（支持 id 和 code 两种键）
  const sdToDomainKey = new Map()
  subDomains.forEach(sd => {
    if (sd?.code) {
      if (sd.domain_id !== undefined) sdToDomainKey.set(sd.code, { kind: 'id', value: sd.domain_id })
      else if (sd.domain_code) sdToDomainKey.set(sd.code, { kind: 'code', value: sd.domain_code })
    }
  })

  const smToSubDomainKey = new Map()
  serviceModules.forEach(sm => {
    if (sm?.code) {
      if (sm.sub_domain_id !== undefined) smToSubDomainKey.set(sm.code, { kind: 'id', value: sm.sub_domain_id })
      else if (sm.sub_domain_code) smToSubDomainKey.set(sm.code, { kind: 'code', value: sm.sub_domain_code })
    }
  })

  const boToServiceModuleKey = new Map()
  businessObjects.forEach(bo => {
    if (bo?.code) {
      if (bo.service_module_id !== undefined) boToServiceModuleKey.set(bo.code, { kind: 'id', value: bo.service_module_id })
      else if (bo.service_module_code) boToServiceModuleKey.set(bo.code, { kind: 'code', value: bo.service_module_code })
    }
  })

  // 构建 id→code 查找表
  const sdIdToCode = new Map()
  subDomains.forEach(sd => { if (sd?.id !== undefined && sd?.code) sdIdToCode.set(sd.id, sd.code) })

  const smIdToCode = new Map()
  serviceModules.forEach(sm => { if (sm?.id !== undefined && sm?.code) smIdToCode.set(sm.id, sm.code) })

  // 判断 SM 是否有有效 BO（businessObject 图专用）
  const smHasBO = new Map()
  if (businessObjectChart) {
    businessObjects.forEach(bo => {
      const key = boToServiceModuleKey.get(bo.code)
      if (!key) return
      const smCode = key.kind === 'id' ? smIdToCode.get(key.value) : key.value
      if (smCode) smHasBO.set(smCode, true)
    })
  }

  // 判断 subDomain 是否有有效 SM
  const sdHasSM = new Map()
  if (businessObjectChart) {
    serviceModules.forEach(sm => {
      if (!sm?.code) return
      if (!smHasBO.has(sm.code)) return
      const key = smToSubDomainKey.get(sm.code)
      if (!key) return
      const sdCode = key.kind === 'id' ? sdIdToCode.get(key.value) : key.value
      if (sdCode) sdHasSM.set(sdCode, true)
    })
  }

  // 判断 domain 是否有有效 subDomain
  const dHasSD = new Map()
  if (businessObjectChart) {
    subDomains.forEach(sd => {
      if (!sd?.code) return
      if (!sdHasSM.has(sd.code)) return
      const key = sdToDomainKey.get(sd.code)
      if (!key) return
      const dCode = key.kind === 'id' ? (() => {
        for (const d of domains) if (d.id === key.value) return d.code
        return null
      })() : key.value
      if (dCode) dHasSD.set(dCode, true)
    })
  }

  // 构建 Group 树
  // 顺序: domain → subDomain → serviceModule → businessObject
  const result = []

  domains.forEach(domain => {
    if (!domain?.code) return
    // businessObject 图：过滤无 BO 的 domain
    if (businessObjectChart && !dHasSD.has(domain.code)) return

    const dChildren = []
    const dContainers = []

    // 找该 domain 下的 subDomains
    const ownedSubDomains = subDomains.filter(sd => {
      if (!sd?.code) return false
      if (businessObjectChart && !sdHasSM.has(sd.code)) return false
      const key = sdToDomainKey.get(sd.code)
      if (!key) return false
      if (key.kind === 'id') return key.value === domain.id
      return key.value === domain.code
    })

    ownedSubDomains.forEach(sd => {
      const sdChildren = []
      const sdContainers = []

      // 找该 sd 下的 serviceModules
      const ownedSMs = serviceModules.filter(sm => {
        if (!sm?.code) return false
        if (businessObjectChart && !smHasBO.has(sm.code)) return false
        const key = smToSubDomainKey.get(sm.code)
        if (!key) return false
        if (key.kind === 'id') return key.value === sd.id
        return key.value === sd.code
      })

      ownedSMs.forEach(sm => {
        const smChildren = []
        const smContainers = []

        // 找该 SM 下的 businessObjects（用 boByCode 去重，保留首个）
        const ownedBOs = []
        const seenBOCodes = new Set()
        businessObjects.forEach(bo => {
          if (!bo?.code || seenBOCodes.has(bo.code)) return
          const key = boToServiceModuleKey.get(bo.code)
          if (!key) return
          if (key.kind === 'id') {
            if (key.value !== sm.id) return
          } else {
            if (key.value !== sm.code) return
          }
          seenBOCodes.add(bo.code)
          ownedBOs.push(bo)
        })

        // businessObject 图：BO 作为 children
        if (businessObjectChart) {
          ownedBOs.forEach(bo => {
            const boGroup = createGroup({
              type: GroupType.BUSINESS_OBJECT,
              title: bo.name || bo.code,
              elementRef: {
                type: GroupType.BUSINESS_OBJECT,
                code: bo.code,
                name: bo.name,
                id: bo.id,
                parentCode: sm.code
              },
              children: []
            })
            smChildren.push(boGroup)
          })
        } else {
          // serviceModule 图：SM 是末端节点，本身不放 BO
          // SM 仍可能有子结构，按 GroupModel 兼容设计放 containers
        }

        const smGroup = createGroup({
          type: GroupType.SERVICE_MODULE,
          title: sm.name || sm.code,
          elementRef: {
            type: GroupType.SERVICE_MODULE,
            code: sm.code,
            name: sm.name,
            id: sm.id,
            parentCode: sd.code
          },
          children: smChildren,
          containers: smContainers
        })

        // serviceModule 图：SM 放 containers
        if (!businessObjectChart) {
          sdContainers.push(smGroup)
        } else {
          sdChildren.push(smGroup)
        }
      })

      const sdGroup = createGroup({
        type: GroupType.SUB_DOMAIN,
        title: sd.name || sd.code,
        elementRef: {
          type: GroupType.SUB_DOMAIN,
          code: sd.code,
          name: sd.name,
          id: sd.id,
          parentCode: domain.code
        },
        children: sdChildren,
        containers: sdContainers
      })
      dChildren.push(sdGroup)
    })

    const dGroup = createGroup({
      type: GroupType.DOMAIN,
      title: domain.name || domain.code,
      elementRef: {
        type: GroupType.DOMAIN,
        code: domain.code,
        name: domain.name,
        id: domain.id
      },
      children: dChildren,
      containers: dContainers
    })
    result.push(dGroup)
  })

  // 建立 parentId 链路
  const setParent = (groups, parent) => {
    groups.forEach(g => {
      g.parentId = parent ? parent.id : null
      setParent(g.children, g)
      setParent(g.containers, g)
    })
  }
  setParent(result, null)

  return result
}

/**
 * 从 previewData (嵌套结构) 反推扁平结构
 *
 * 用于兼容 buildDomainProducts 等老 API 输出 (dataFlowLayer 2 中间产物)
 *
 * @param {Object} previewData - { domainProducts: [...] }
 * @returns {Object} flattenData - { domains, subDomains, serviceModules, businessObjects }
 */
export function previewDataToFlatten(previewData) {
  const empty = {
    domains: [],
    subDomains: [],
    serviceModules: [],
    businessObjects: []
  }

  if (!previewData || !Array.isArray(previewData.domainProducts)) {
    return empty
  }

  const domains = []
  const subDomains = []
  const serviceModules = []
  const businessObjects = []

  // code 去重
  const seenDomain = new Set()
  const seenSD = new Set()
  const seenSM = new Set()
  const seenBO = new Set()

  for (const dp of previewData.domainProducts) {
    if (!dp?.code || seenDomain.has(dp.code)) continue
    seenDomain.add(dp.code)
    domains.push({ code: dp.code, name: dp.name, id: dp.id })

    const modules = Array.isArray(dp.modules) ? dp.modules : []
    for (const mod of modules) {
      if (!mod?.code || seenSD.has(mod.code)) continue
      seenSD.add(mod.code)
      subDomains.push({
        code: mod.code,
        name: mod.name,
        id: mod.id,
        domain_code: dp.code
      })

      const submodules = Array.isArray(mod.submodules) ? mod.submodules : []
      for (const sm of submodules) {
        if (!sm?.code || seenSM.has(sm.code)) continue
        seenSM.add(sm.code)
        serviceModules.push({
          code: sm.code,
          name: sm.name,
          id: sm.id,
          sub_domain_code: mod.code
        })

        const bos = Array.isArray(sm.businessObjects) ? sm.businessObjects : []
        for (const bo of bos) {
          if (!bo?.code || seenBO.has(bo.code)) continue
          seenBO.add(bo.code)
          businessObjects.push({
            code: bo.code,
            name: bo.name,
            id: bo.id,
            service_module_code: sm.code
          })
        }
      }
    }
  }

  return { domains, subDomains, serviceModules, businessObjects }
}

/**
 * 从扁平 relationships 提取 Link 数组
 *
 * 输入兼容两种格式：
 *   - camelCase: { sourceCode, targetCode, relationCode, ... }
 *   - snake_case: { source_bo_id, target_bo_id, relation_code, ... } (fetchPreviewData 原始输出)
 *
 * 输出统一 Link 结构：
 *   { source, target, relationCode, label?, categoryTypes?, annotationContents?, relationDesc? }
 *
 * 契约见 chart-data-flow-and-interaction-upgrade.md §5.10.2 ②
 *
 * @param {Array} relationships - 关系数组
 * @returns {Array} Link[] - 统一格式的链接数组
 */
export function extractLinks(relationships) {
  if (!Array.isArray(relationships)) return []

  const seen = new Set()
  const links = []

  for (const rel of relationships) {
    if (!rel || typeof rel !== 'object') continue

    // 兼容 snake_case 和 camelCase
    const source = rel.sourceCode ?? rel.source_code ?? rel.source_bo_id ?? rel.source ?? null
    const target = rel.targetCode ?? rel.target_code ?? rel.target_bo_id ?? rel.target ?? null
    const relationCode = rel.relationCode ?? rel.relation_code ?? null

    // 边界 1: sourceCode/targetCode 为空跳过
    if (!source || !target) continue

    // 边界 2: 自环跳过
    if (source === target) continue

    // 边界 3: 同 source/target/relationCode 去重
    const dedupeKey = `${source}|${target}|${relationCode || ''}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)

    // 反向关系不视为重复（key 不同）

    const label = rel.label ?? rel.relationDesc ?? rel.relation_desc ?? relationCode ?? ''
    const categoryTypes = rel.categoryTypes ?? rel.category_types ?? rel.annotationCategories ?? rel.annotation_categories ?? []
    const annotationContents = rel.annotationContents ?? rel.annotation_contents ?? []

    links.push({
      source,
      target,
      relationCode,
      label,
      categoryTypes,
      annotationContents,
      relationDesc: rel.relationDesc ?? rel.relation_desc ?? ''
    })
  }

  return links
}
