/**
 * [FIX 2026-07-29 v5] GroupModel → LayoutControlPanel 适配层
 *
 * 背景：
 *   - GroupModel.toMermaidConfig 输出用 `containers` 字段承载嵌套结构（type 大写枚举）
 *   - LayoutControlPanel/GroupItem 期望用 `children`（非终端子分组）+ `containers`（终端叶子节点），
 *     且 groupType 小写、需要 domainName/subDomainName/serviceModuleName 用于着色
 *   - 直接把 GroupModel 输出喂给 LayoutControlPanel 会导致 onMounted 检测 groups 为空（结构不匹配）
 *     → 触发 handleServiceModuleAutoGroup → emitUpdate → 图表刷新
 *
 * 方案 B（隔离适配层）：
 *   新增本纯函数 adaptGroupModelForLayoutPanel，把 GroupModel 输出转换为 LayoutControlPanel 期望的格式。
 *   仅用于 SM 图（EmbeddedChartView.syncLayoutControlFromDiagramData 在 chartType='serviceModule' 时调用）。
 *   BO 图保持走 buildBusinessObjectGroups 原路径不变（GroupModel 输出会丢失 BO 终端节点，不复用）。
 *
 * 转换规则：
 *   - type → groupType: DOMAIN→domain, SUB_DOMAIN→subDomain, SERVICE_MODULE→serviceModule, BUSINESS_OBJECT→custom
 *   - containers 拆分：
 *       * BUSINESS_OBJECT 类型 → 终端叶子节点，留在 `containers`（与 BO 图 buildBusinessObjectGroups 一致）
 *       * 其他类型（DOMAIN/SUB_DOMAIN/SERVICE_MODULE）→ 非终端子分组，递归转换后放入 `children`
 *   - SM 图关键：SUB_DOMAIN.containers=[SM_config]，SM 视为子分组放入 children（而非终端容器），
 *     这样 GroupItem 才能按 groupType='serviceModule' 渲染 SM 为叶子分组（containers 为空）。
 *   - domainName/subDomainName/serviceModuleName：从父级上下文派生（DOMAIN 设 domainName，
 *     SUB_DOMAIN 设 subDomainName 并继承 domainName，SERVICE_MODULE 设 serviceModuleName 并继承前两者）。
 */

import { GroupType, isTerminalGroup, createGroupId } from './types.js'

/**
 * 把 GroupModel.toMermaidConfig 的输出转换为 LayoutControlPanel 期望的嵌套分组结构
 *
 * @param {Array} mermaidGroups - GroupModel.toMermaidConfig() 输出（用 containers 嵌套）
 * @param {string} chartType - 图表类型 'serviceModule' | 'businessObject'
 * @returns {Array} groups - LayoutControlPanel 期望的嵌套分组树（children + containers）
 */
export function adaptGroupModelForLayoutPanel(mermaidGroups, chartType) {
  if (!Array.isArray(mermaidGroups) || mermaidGroups.length === 0) return []

  // type → groupType 映射
  const typeToGroupType = {
    [GroupType.DOMAIN]: 'domain',
    [GroupType.SUB_DOMAIN]: 'subDomain',
    [GroupType.SERVICE_MODULE]: 'serviceModule',
    [GroupType.BUSINESS_OBJECT]: 'custom',
    [GroupType.CUSTOM]: 'custom'
  }

  /**
   * 判断容器是否为"终端叶子节点"（放入 containers 字段，而非递归到 children）
   * 与 types.js 的 isTerminalGroup 保持一致：
   *   - SM 图 (chartType='serviceModule'): SERVICE_MODULE 是终端 → 放入 containers
   *   - BO 图 (chartType='businessObject'): BUSINESS_OBJECT 是终端 → 放入 containers
   *
   * [FIX 2026-07-29 v5.1] 之前硬编码只把 BUSINESS_OBJECT 当终端，导致 SM 图的 SM 被放入 children，
   *   LayoutControlPanel.countServiceModulesInGroups 只在 containers 里数 SM → 返回 0
   *   → needReGroup=true → handleAutoGroupByDomain → emitUpdate → generateDiagram → 图表刷新。
   *   修复：用 isTerminalGroup(container, chartType) 按 chartType 判定终端。
   */
  function isTerminalContainer(container) {
    return isTerminalGroup(container, chartType)
  }

  /**
   * 递归转换单个分组
   * @param {Object} group - GroupModel.toMermaidConfig 输出的单个分组
   * @param {Object} parentContext - 父级派生字段 { domainName, subDomainName, serviceModuleName }
   * @returns {Object|null} LayoutControlPanel 格式的分组
   */
  function convertGroup(group, parentContext = {}) {
    if (!group) return null

    const groupType = typeToGroupType[group.type] || 'custom'

    // 派生 domainName/subDomainName/serviceModuleName
    // 使用 group.name（原始标题，不含 disabled 路径）以保证着色 key 稳定
    const rawName = group.name || group.title || ''
    let domainName = parentContext.domainName
    let subDomainName = parentContext.subDomainName
    let serviceModuleName = parentContext.serviceModuleName

    if (group.type === GroupType.DOMAIN) {
      domainName = rawName
    } else if (group.type === GroupType.SUB_DOMAIN) {
      subDomainName = rawName
      // domainName 继承自父级
    } else if (group.type === GroupType.SERVICE_MODULE) {
      serviceModuleName = rawName
      // domainName / subDomainName 继承自父级
    }
    // BUSINESS_OBJECT / CUSTOM: 全部继承自父级

    const currentContext = { domainName, subDomainName, serviceModuleName }

    // 拆分 containers：终端 → containers，非终端 → 递归到 children
    const childGroups = []
    const terminalContainers = []

    if (group.containers && group.containers.length > 0) {
      for (const container of group.containers) {
        if (isTerminalContainer(container)) {
          // 终端叶子节点（SM 图的 SM / BO 图的 BO）：转换为 LayoutControlPanel 期望格式后放入 containers
          //   [FIX v5.1] 之前原样 push，导致终端容器缺少 groupType 字段，
          //   countServiceModulesInGroups 检查 `c.groupType === 'serviceModule'` 失败 → needReGroup=true
          const terminalGroupType = typeToGroupType[container.type] || 'custom'
          // 终端节点的 domainName/subDomainName/serviceModuleName 继承自父级上下文
          //   对于 SM 图的 SM：serviceModuleName 用自己的 name（与 handleServiceModuleAutoGroup 一致）
          let termDomainName = domainName
          let termSubDomainName = subDomainName
          let termServiceModuleName = serviceModuleName
          if (container.type === GroupType.SERVICE_MODULE) {
            termServiceModuleName = container.name || container.title || ''
          }
          terminalContainers.push({
            id: container.id,
            title: container.title || container.name || '',
            elementCode: container.elementCode,
            type: container.type, // 保留原始 type（大写枚举），供 hasGroupContent 等使用
            groupType: terminalGroupType, // 新增：小写 groupType，供 countServiceModulesInGroups 使用
            domainName: termDomainName,
            subDomainName: termSubDomainName,
            serviceModuleName: termServiceModuleName,
            direction: container.direction || 'TB',
            visible: container.visible !== false,
            enabled: container.enabled !== false,
            style: container.style || {},
            containers: [],
            children: [],
            parentId: null
          })
        } else {
          // 非终端子分组：递归转换后放入 children
          const childConfig = convertGroup(container, currentContext)
          if (childConfig) {
            childGroups.push(childConfig)
          }
        }
      }
    }

    return {
      id: group.id,
      title: group.title || group.name || '',
      elementCode: group.elementCode,
      groupType,
      domainName,
      subDomainName,
      serviceModuleName,
      direction: group.direction || 'TB',
      visible: group.visible !== false,
      enabled: group.enabled !== false,
      style: group.style || {},
      containers: terminalContainers,
      children: childGroups,
      // parentId 在 LayoutControlPanel 内通过 findGroupById 重建，这里设 null 即可
      parentId: null
    }
  }

  const result = []
  for (const group of mermaidGroups) {
    const converted = convertGroup(group, {})
    if (converted) {
      result.push(converted)
    }
  }
  return result
}

/**
 * [FIX 2026-07-30 v7] 提取 groups 中各分组的 enabled/visible 状态（按 elementCode 索引）
 *
 * 用途：切换图表类型（如 BO→SM）时，旧 groups 即将被重新生成覆盖，
 *   先调用本函数快照状态，新 groups 生成后用 applyGroupStates 应用，
 *   保留用户的 disable 配置（如"供应链云 disabled"）。
 *
 * 递归遍历 children（非终端子分组）和 containers（终端叶子），收集所有分组的
 *   { elementCode: { enabled, visible } }。elementCode 在 BO/SM 图都存在且稳定，
 *   可跨图表类型匹配（如 BO 图和 SM 图的"供应链云" domain.code 相同）。
 *
 * @param {Array} groups - 旧 groups
 * @returns {Map<string, {enabled: boolean, visible: boolean}>} elementCode → 状态
 */
// [FIX 2026-08-12] 状态键必须含层级(groupType)以消除编码歧义:
//   SM/ITTF 等编码会在"子领域"与"服务模块"两个层级重复出现
//   (如 子领域"销售"=SM 与 服务模块"服务管理"=SM; 子领域"内部交易"=ITTF 与
//   服务模块"内部交易"=ITTF). 若仅用 elementCode 作 Map 键, 二者会合并成一条状态,
//   导致子领域展开状态被同码服务模块覆盖 → 双击子领域无响应(渲染层 sig 不变).
//   键格式: "<code>::<groupType规范化>", 无 groupType/type 时退回纯 code (兼容 legacy/BO 叶).
//   extract 与 apply 必须共用本函数, 保证两棵树的同一逻辑节点匹配到同一 key.
export function groupStateKey(item) {
  if (!item) return null
  const base = item.elementCode || item.id
  if (base == null) return null
  const raw = item.groupType || item.type || ''
  const gt = String(raw).toLowerCase().replace(/_/g, '')
  return gt ? `${String(base)}::${gt}` : String(base)
}

export function extractGroupStates(groups) {
  const states = new Map()
  if (!groups || !Array.isArray(groups)) return states

  function traverse(items) {
    if (!Array.isArray(items)) return
    for (const item of items) {
      if (!item) continue
      const key = groupStateKey(item)
      if (key) {
        states.set(key, {
          enabled: item.enabled !== undefined ? item.enabled : true,
          visible: item.visible !== undefined ? item.visible : true,
          // [FOLD 2026-08-05] 保留折叠状态, 否则折叠/展开在跨管道合并时丢失 (FR-002 断点).
          //   applyViewTemplate / setSubtreeCollapsed 只改 chartConfig.layoutControl.groups,
          //   渲染用的 merged groups 由 extract/apply 状态链路承载, 必须含 collapsed.
          collapsed: item.collapsed !== undefined ? item.collapsed : false
        })
      }
      if (item.children && item.children.length > 0) traverse(item.children)
      if (item.containers && item.containers.length > 0) traverse(item.containers)
    }
  }
  traverse(groups)
  return states
}

/**
 * [FIX 2026-07-30 v7] 把旧 groups 的 enabled/visible 状态应用到新 groups
 *
 * 按 elementCode 匹配，只更新状态字段，不改变分组结构。
 * 与 extractGroupStates 配合使用，实现跨图表类型的状态迁移。
 *
 * @param {Array} groups - 新 groups（会被原地修改）
 * @param {Map<string, {enabled: boolean, visible: boolean}>} states - 旧状态
 * @returns {number} 实际应用的节点数（用于诊断）
 */
export function applyGroupStates(groups, states) {
  if (!groups || !Array.isArray(groups) || !states || states.size === 0) return 0

  let applied = 0
  function traverse(items) {
    if (!Array.isArray(items)) return
    for (const item of items) {
      if (!item) continue
      const key = groupStateKey(item)
      if (key && states.has(key)) {
        const state = states.get(key)
        item.enabled = state.enabled
        item.visible = state.visible
        // [FOLD 2026-08-05] 与 extractGroupStates 对应, 回填折叠状态
        item.collapsed = state.collapsed
        applied++
      }
      if (item.children && item.children.length > 0) traverse(item.children)
      if (item.containers && item.containers.length > 0) traverse(item.containers)
    }
  }
  traverse(groups)
  return applied
}

/**
 * [FIX 2026-07-30 v8] 从 domainProducts 直接构建 SM 图分组树
 *
 * 背景：
 *   之前 syncLayoutControlFromDiagramData 对 SM 图用 adaptGroupModelForLayoutPanel
 *   转换 GroupModel.toMermaidConfig 输出。但 GroupModel.toMermaidConfig 会过滤掉 disabled
 *   分组（L466-468 返回 null），导致 disabled 的"供应链云"在 SM 图 groups 中丢失，
 *   applyGroupStates 找不到匹配项 → 状态迁移失败 → 切回 BO 图时 disabled 状态丢失（循环依赖）。
 *
 *   根因：GroupModel.toMermaidConfig 的输出是为"渲染"设计的（disabled 分组不渲染），
 *   不适合作为"布局控制面板"的数据源（面板需要展示所有分组，包括 disabled 的）。
 *
 *   修复：syncLayoutControlFromDiagramData 对 SM 图改用本函数从 domainProducts 直接构建，
 *   不依赖 GroupModel 输出，从而保留所有 domain（包括 disabled 的）。
 *   与 LayoutControlPanel.handleServiceModuleAutoGroup 共享同一逻辑，保证结构一致。
 *
 * 结构：领域 → 子领域 → 服务模块（始终三层，即使只有一个子领域也创建完整结构）
 *   - domain (groupType='domain') → children: [subDomain]
 *   - subDomain (groupType='subDomain') → containers: [SM]
 *   - SM (groupType='serviceModule') → 终端叶子（containers/children 为空）
 *
 * @param {Array} domainProducts - 领域树 [{name, code, modules: [{name, code, submodules: [{name, code}]}]}]
 * @returns {Array} groups - LayoutControlPanel 期望的嵌套分组树
 */
export function buildServiceModuleGroupsFromDomainProducts(domainProducts) {
  if (!Array.isArray(domainProducts) || domainProducts.length === 0) return []

  const groups = []

  domainProducts.forEach(domain => {
    const domainName = domain.name || '未分类'
    const domainCode = domain.code || domainName
    const domainId = createGroupId(GroupType.DOMAIN, domainCode)

    // 创建领域分组
    const domainGroup = {
      id: domainId,
      title: domainName,
      elementCode: domainCode,
      groupType: 'domain',
      direction: 'LR',
      visible: true,
      enabled: true,
      collapsed: false, // [FOLD 2026-08-05] 折叠语义: 折叠为单节点
      style: {
        fill: '#f5f5f5',
        stroke: '#333333',
        strokeWidth: 2,
        strokeDasharray: ''
      },
      containers: [],
      children: [],
      parentId: null
    }

    domain.modules?.forEach(subDomain => {
      const subDomainName = subDomain.name || '未分类'
      const subDomainCode = subDomain.code || subDomainName
      const subDomainId = createGroupId(GroupType.SUB_DOMAIN, subDomainCode)

      // 创建子领域分组
      const subDomainGroup = {
        id: subDomainId,
        title: subDomainName,
        elementCode: subDomainCode,
        groupType: 'subDomain',
        direction: 'TB',
        visible: true,
        enabled: true,
        collapsed: false, // [FOLD 2026-08-05] 折叠语义: 折叠为单节点
        style: {
          fill: '#ffffff',
          stroke: '#666666',
          strokeWidth: 2,
          strokeDasharray: ''
        },
        containers: [],
        children: [],
        parentId: domainGroup.id
      }

      // 服务模块：作为 containers 节点（终端叶子，与 buildServiceModuleGroupModel 一致）
      subDomain.submodules?.forEach(sm => {
        const smCode = sm.code || sm.name
        const smName = sm.name || sm.code
        const smId = createGroupId(GroupType.SERVICE_MODULE, smCode)

        subDomainGroup.containers.push({
          id: smId,
          type: GroupType.SERVICE_MODULE,
          title: smName,
          elementCode: smCode,
          elementRef: {
            type: GroupType.SERVICE_MODULE,
            code: smCode,
            name: smName
          },
          parentId: subDomainGroup.id,
          groupType: 'serviceModule',
          direction: 'TB',
          visible: true,
          enabled: true,
          collapsed: false, // [FOLD 2026-08-05] 折叠语义: 折叠为单节点
          style: {
            fill: '#ffffff',
            stroke: '#666666',
            strokeWidth: 1,
            strokeDasharray: ''
          },
          containers: [],
          children: []
        })
      })
      if (subDomainGroup.containers.length > 0) {
        domainGroup.children.push(subDomainGroup)
      }
    })

    if (domainGroup.children.length > 0) {
      groups.push(domainGroup)
    }
  })

  return groups
}
