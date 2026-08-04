/**
 * [FIX 2026-07-29 v4] 业务对象图自动分组工具函数
 *
 * 背景：
 *   - LayoutControlPanel.handleBusinessObjectAutoGroup 依赖 props.containers/props.links
 *   - EmbeddedChartView.onMounted 也需要预生成分组布局数据模型（v3 架构调整）
 *   - 两套组件需要共享同一套分组生成逻辑，避免重复代码
 *
 * 解决方案：
 *   - 把 handleBusinessObjectAutoGroup 的核心逻辑提取到本模块
 *   - EmbeddedChartView.onMounted.syncLayoutControlFromDiagramData 直接调用 buildBusinessObjectGroups
 *   - LayoutControlPanel.handleBusinessObjectAutoGroup 改为调用 buildBusinessObjectGroups + 写 localConfig
 *
 * 输入：containers（嵌套 [{domain, domainCode, id, name, nodes, serviceModuleMap}]）、links（关系）
 * 输出：groups（嵌套分组树）
 *   - domain → subDomain → serviceModule → BO 节点（containers 字段）
 *   - serviceModule 下还有 ELK inner/boundary 子分组
 *
 * 约束：与 LayoutControlPanel.handleBusinessObjectAutoGroup 保持一致的输出结构
 *       （groupType: 'domain'|'subDomain'|'serviceModule'|'custom'）
 */

import { GroupType, createGroupId } from '@/services/groupModel/types.js'

/**
 * 构建业务对象图的自动分组
 *
 * @param {Array} containers - 嵌套的容器数组 [{domain, domainCode, id, name, nodes, serviceModuleMap}]
 * @param {Array} links - 关系连线数组 [{source, target, ...}]
 * @returns {Array} groups - 嵌套分组树
 */
export function buildBusinessObjectGroups(containers = [], links = []) {
  if (!containers || containers.length === 0) return []

  // 构建节点编码到名称的映射
  const codeToNameMap = new Map()
  containers.forEach(container => {
    // [FIX 2026-08-04] 优先用 container.nodeNames (从 diagramData.nodes 派生的 BO 编码→名称映射)
    //   BO nodes 是字符串 (编码), 之前直接用 node (编码) 作为名称 → name=code → 显示只有编码
    if (container.nodeNames) {
      Object.entries(container.nodeNames).forEach(([code, name]) => {
        if (code && name) codeToNameMap.set(code, name)
      })
    }
    if (container.nodes) {
      container.nodes.forEach(node => {
        const nodeCode = typeof node === 'string' ? node : (node.code || node.id)
        const nodeName = typeof node === 'string' ? node : (node.name || node.code || node.id)
        if (nodeCode && !codeToNameMap.has(nodeCode)) {
          codeToNameMap.set(nodeCode, nodeName)
        }
      })
    }
  })

  // 构建 domainMap 结构（用于后续判断服务模块）
  const domainMap = new Map()

  containers.forEach(container => {
    const domainName = container.domain || '未分类'
    const domainCode = container.domainCode || domainName
    const subDomainName = container.name
    const subDomainCode = container.id || subDomainName
    const serviceModuleMap = container.serviceModuleMap || {}

    if (!domainMap.has(domainName)) {
      domainMap.set(domainName, {
        subDomainMap: new Map(),
        domainCode: domainCode
      })
    }
    const subDomainMap = domainMap.get(domainName).subDomainMap

    if (!subDomainMap.has(subDomainName)) {
      subDomainMap.set(subDomainName, {
        smMap: new Map(),
        subDomainCode: subDomainCode
      })
    }
    const smMap = subDomainMap.get(subDomainName).smMap

    Object.entries(serviceModuleMap).forEach(([smName, smData]) => {
      const boNodes = smData.nodes || smData
      const boCodes = Array.isArray(boNodes)
        ? boNodes.map(node => typeof node === 'string' ? node : (node.code || node.id))
        : []
      const smCode = smData.code || smName
      if (!smMap.has(smName)) {
        smMap.set(smName, { boCodes: [], smCode: smCode })
      }
      smMap.get(smName).boCodes.push(...boCodes)
    })

    // 如果没有 serviceModuleMap，直接使用 container.nodes
    if (Object.keys(serviceModuleMap).length === 0 && container.nodes) {
      const allNodeCodes = container.nodes.map(node => typeof node === 'string' ? node : (node.code || node.id))
      if (!smMap.has(subDomainName)) {
        smMap.set(subDomainName, { boCodes: [], smCode: subDomainCode })
      }
      smMap.get(subDomainName).boCodes.push(...allNodeCodes)
    }
  })

  // 构建节点到服务模块的映射（用于判断外部连线）
  const nodeToServiceModuleMap = new Map()
  domainMap.forEach((domainData, domainName) => {
    domainData.subDomainMap.forEach((subDomainData, subDomainName) => {
      subDomainData.smMap.forEach((smData, smName) => {
        smData.boCodes.forEach(boCode => {
          nodeToServiceModuleMap.set(boCode, smName)
        })
      })
    })
  })

  // 计算每个服务模块的节点，并标记有外部连线的节点
  const nodesWithExternalLinks = new Set()
  const sourceToServiceModuleMap = new Map()

  // 构建 source/target → 节点编码 的映射
  const allNodeCodes = new Set()
  domainMap.forEach((domainData) => {
    domainData.subDomainMap.forEach((subDomainData) => {
      subDomainData.smMap.forEach((smData) => {
        smData.boCodes.forEach(code => allNodeCodes.add(code))
      })
    })
  })

  // 识别有外部连线的节点（连线两端不在同一服务模块）
  links.forEach(link => {
    const sourceCode = link.sourceCode || link.source
    const targetCode = link.targetCode || link.target

    if (sourceCode && allNodeCodes.has(sourceCode) && targetCode && allNodeCodes.has(targetCode)) {
      const sourceSm = nodeToServiceModuleMap.get(sourceCode)
      const targetSm = nodeToServiceModuleMap.get(targetCode)

      if (sourceSm && targetSm && sourceSm !== targetSm) {
        nodesWithExternalLinks.add(sourceCode)
        nodesWithExternalLinks.add(targetCode)
      }
    }
  })

  // 构建分组
  const groups = []

  domainMap.forEach((domainData, domainName) => {
    const { subDomainMap, domainCode } = domainData
    const childGroups = []

    subDomainMap.forEach((subDomainData, subDomainName) => {
      const { smMap, subDomainCode } = subDomainData
      const smChildGroups = []

      smMap.forEach((smData, smName) => {
        const { boCodes, smCode } = smData

        // ELK 自动分组：将有/无外部连线的节点分离
        const innerNodes = boCodes.filter(code => !nodesWithExternalLinks.has(code))
        const boundaryNodes = boCodes.filter(code => nodesWithExternalLinks.has(code))

        // 创建容器对象（供后续分组使用）
        const createNodeContainer = (boCode, elkType) => ({
          id: `bo_${boCode}_${elkType}`,
          name: codeToNameMap.get(boCode) || boCode,
          elementCode: boCode,
          isVirtual: true,
          nodes: [boCode],
          domain: domainName,
          subDomainName: subDomainName,
          serviceModuleName: smName,
          _elkGroup: elkType
        })

        // 内部节点容器（无外部连线）
        const innerContainers = innerNodes.map(code => createNodeContainer(code, 'inner'))
        // 边界节点容器（有外部连线）
        const boundaryContainers = boundaryNodes.map(code => createNodeContainer(code, 'boundary'))

        // 创建 ELK 子分组
        const createElkSubGroup = (title, containers, elkType) => ({
          id: createGroupId(GroupType.CUSTOM, `${smCode}_${elkType}`),
          title,
          elementCode: `${smCode}_${elkType}`,
          groupType: 'custom',
          domainName,
          subDomainName,
          serviceModuleName: smName,
          direction: 'TB',
          visible: false,  // 默认隐藏
          enabled: true,
          style: {
            fill: elkType === 'inner' ? '#e8f5e9' : '#fff3e0',
            stroke: elkType === 'inner' ? '#4caf50' : '#ff9800',
            strokeWidth: 1,
            strokeDasharray: ''
          },
          containers,
          children: [],
          parentId: null,  // 稍后设置
          _elkGroup: elkType
        })

        // 内部子分组（无外部关系）
        const innerGroup = createElkSubGroup('无外部关系', innerContainers, 'inner')
        // 边界子分组（有外部关系）
        const boundaryGroup = createElkSubGroup('有外部关系', boundaryContainers, 'boundary')

        // 根据是否有两类节点决定分组结构
        const hasInner = innerNodes.length > 0
        const hasBoundary = boundaryNodes.length > 0

        if (hasInner && hasBoundary) {
          // 两类节点都存在：创建父子分组结构
          const parentGroupId = createGroupId(GroupType.SERVICE_MODULE, smCode)
          innerGroup.parentId = parentGroupId
          boundaryGroup.parentId = parentGroupId

          const parentGroup = {
            id: parentGroupId,
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: [],
            children: [innerGroup, boundaryGroup],
            parentId: null
          }
          smChildGroups.push(parentGroup)
        } else if (hasInner) {
          // 只有无外部关系节点：只创建无外部关系分组（平铺，不嵌套）
          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: innerContainers,
            children: [],
            parentId: null,
            _elkGroup: 'inner'  // 标记为 ELK 分组
          })
        } else if (hasBoundary) {
          // 只有有外部关系节点：只创建有外部关系分组（平铺，不嵌套）
          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: boundaryContainers,
            children: [],
            parentId: null,
            _elkGroup: 'boundary'  // 标记为 ELK 分组
          })
        } else {
          // 不分离，保持原样 - 使用节点名称（没有外部连线数据时）
          const virtualContainers = boCodes.map(boCode => ({
            id: `bo_${boCode}`,
            name: codeToNameMap.get(boCode) || boCode,
            elementCode: boCode,
            isVirtual: true,
            nodes: [boCode],
            domain: domainName,
            subDomainName: subDomainName,
            serviceModuleName: smName
          }))

          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName: domainName,
            subDomainName: subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: virtualContainers,
            children: [],
            parentId: null
          })
        }
      })

      childGroups.push({
        id: createGroupId(GroupType.SUB_DOMAIN, subDomainCode),
        title: subDomainName,
        elementCode: subDomainCode,
        groupType: 'subDomain',
        domainName: domainName,
        subDomainName: subDomainName,
        direction: 'LR',
        visible: true,
        enabled: true,
        style: {
          fill: '#ffffff',
          stroke: '#666666',
          strokeWidth: 2,
          strokeDasharray: ''
        },
        containers: [],
        children: smChildGroups,
        parentId: null
      })
    })

    const group = {
      id: createGroupId(GroupType.DOMAIN, domainCode),
      title: domainName,
      elementCode: domainCode,
      groupType: 'domain',
      domainName: domainName,
      direction: 'TB',
      visible: true,
      enabled: true,
      style: {
        fill: '#f5f5f5',
        stroke: '#333333',
        strokeWidth: 2,
        strokeDasharray: ''
      },
      containers: [],
      children: childGroups,
      parentId: null
    }

    groups.push(group)
  })

  return groups
}