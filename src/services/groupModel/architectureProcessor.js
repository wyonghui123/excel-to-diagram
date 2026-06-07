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
