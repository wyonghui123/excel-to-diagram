import { getColors, assignColorsToGroups, getLinkColor } from './useMermaidColors.js'
import { useBlockDiagramStyle, BLOCK_DIAGRAM_STYLES } from '../style/useBlockDiagramStyle.js'
import { useBlockDiagramSyntax, DIAGRAM_TYPES } from './useBlockDiagramSyntax.js'
import { routeLayout } from '../layouts/index.js'
import { remapLinksToVisibleAncestors, fuseLinks } from '../layouts/linkRemapper.js'
import { recordLinkDiag } from '../core/linkDiagnostics.js'
import { checkDepth, checkCycle, createVisitedSet } from '../../../services/groupModel/safetyUtils.js'
import { DataFlowLogger } from '../../../services/groupModel/dataFlowLogger.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'
import { getArrowSyntax, sanitizeLabel } from './_shared/arrowHelper.js'
import { computeUplift, markUplift, sanitizeId } from '../layouts/upliftDerivation.js'
import { businessObjectLabel } from './nodeLabelTemplate.js'

function sortVirtualContainersBySize(containers) {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  return [...containers].sort((a, b) => {
    const aSize = a.nodes?.length || 0
    const bSize = b.nodes?.length || 0
    return bSize - aSize
  })
}

function calculateContainerConnectionDensity(containers, links) {
  if (!containers || containers.length === 0 || !links || links.length === 0) {
    return new Map()
  }
  
  const densityMap = new Map()
  
  containers.forEach(container => {
    const nodeSet = new Set(container.nodes || [])
    let internalConnections = 0
    let externalConnections = 0
    
    links.forEach(link => {
      const sourceInContainer = nodeSet.has(link.source)
      const targetInContainer = nodeSet.has(link.target)
      
      if (sourceInContainer && targetInContainer) {
        internalConnections++
      } else if (sourceInContainer || targetInContainer) {
        externalConnections++
      }
    })
    
    densityMap.set(container.id, {
      internal: internalConnections,
      external: externalConnections,
      total: internalConnections + externalConnections
    })
  })
  
  return densityMap
}

function sortVirtualContainersByConnection(containers, links) {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  if (!links || links.length === 0) {
    return [...containers]
  }
  
  const densityMap = calculateContainerConnectionDensity(containers, links)
  
  const containerConnections = new Map()
  containers.forEach(container => {
    const nodeSet = new Set(container.nodes || [])
    const connectedContainers = new Set()
    
    links.forEach(link => {
      const sourceInContainer = nodeSet.has(link.source)
      const targetInContainer = nodeSet.has(link.target)
      
      if (sourceInContainer && !targetInContainer) {
        containers.forEach(other => {
          if (other.id !== container.id && other.nodes?.includes(link.target)) {
            connectedContainers.add(other.id)
          }
        })
      } else if (!sourceInContainer && targetInContainer) {
        containers.forEach(other => {
          if (other.id !== container.id && other.nodes?.includes(link.source)) {
            connectedContainers.add(other.id)
          }
        })
      }
    })
    
    containerConnections.set(container.id, connectedContainers)
  })
  
  const sorted = []
  const remaining = [...containers]
  
  let maxConnections = 0
  let startContainer = remaining[0]
  remaining.forEach(container => {
    const connections = containerConnections.get(container.id)?.size || 0
    if (connections > maxConnections) {
      maxConnections = connections
      startContainer = container
    }
  })
  
  sorted.push(startContainer)
  const remainingIdx = remaining.findIndex(c => c.id === startContainer.id)
  remaining.splice(remainingIdx, 1)
  
  while (remaining.length > 0) {
    const lastContainer = sorted[sorted.length - 1]
    const lastConnections = containerConnections.get(lastContainer.id) || new Set()
    
    let bestNext = null
    let bestScore = -1
    
    remaining.forEach(container => {
      if (lastConnections.has(container.id)) {
        const density = densityMap.get(container.id)
        const score = density ? density.total : 0
        if (score > bestScore) {
          bestScore = score
          bestNext = container
        }
      }
    })
    
    if (!bestNext) {
      let maxDensity = -1
      remaining.forEach(container => {
        const density = densityMap.get(container.id)
        const total = density ? density.total : 0
        if (total > maxDensity) {
          maxDensity = total
          bestNext = container
        }
      })
    }
    
    if (bestNext) {
      sorted.push(bestNext)
      const idx = remaining.findIndex(c => c.id === bestNext.id)
      remaining.splice(idx, 1)
    } else {
      sorted.push(remaining.shift())
    }
  }
  
  return sorted
}

function calculateContainerScores(containers, links, weights = { size: 0.4, connection: 0.6 }) {
  if (!containers || containers.length === 0) {
    return new Map()
  }
  
  const scores = new Map()
  
  const maxNodes = Math.max(...containers.map(c => c.nodes?.length || 0), 1)
  
  const densityMap = calculateContainerConnectionDensity(containers, links)
  const maxDensity = Math.max(...Array.from(densityMap.values()).map(d => d.total), 1)
  
  containers.forEach(container => {
    const sizeScore = (container.nodes?.length || 0) / maxNodes
    
    const density = densityMap.get(container.id) || { total: 0 }
    const connectionScore = density.total / maxDensity
    
    const combinedScore = (sizeScore * weights.size) + (connectionScore * weights.connection)
    
    scores.set(container.id, {
      size: sizeScore,
      connection: connectionScore,
      combined: combinedScore
    })
  })
  
  return scores
}

function sortVirtualContainers(containers, links, strategy = 'combined') {
  if (!containers || containers.length === 0) {
    return containers
  }
  
  switch (strategy) {
    case 'size':
      return sortVirtualContainersBySize(containers)
    
    case 'connection':
      return sortVirtualContainersByConnection(containers, links)
    
    case 'combined':
    default:
      const scores = calculateContainerScores(containers, links)
      return [...containers].sort((a, b) => {
        const scoreA = scores.get(a.id)?.combined || 0
        const scoreB = scores.get(b.id)?.combined || 0
        return scoreB - scoreA
      })
  }
}

function collectContainers(group, allContainers, visited = null, depth = 0) {
  if (!group) return
  
  if (!checkDepth(depth, 'BusinessObjectSyntax.collectContainers')) {
    return
  }
  
  if (!visited) {
    visited = createVisitedSet()
  }
  
  if (group.id && checkCycle(group.id, visited, 'BusinessObjectSyntax.collectContainers')) {
    return
  }
  
  if (group.containers && group.containers.length > 0) {
    group.containers.forEach(c => {
      if (c.nodes && c.nodes.length > 0) {
        c._containerLevel = depth + 1
        allContainers.push(c)
      }
    })
  }
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => collectContainers(child, allContainers, visited, depth + 1))
  }
}

function buildVirtualContainers(groups, moduleGroups, businessObjectNodes, nodeNameToIdMap = new Map(), nodeCodeToIdMap = new Map(), titleMap = {}) {
  const usedModules = new Set()
  
  function processGroup(group, visited = null, depth = 0) {
    if (!group) return

    if (!checkDepth(depth, 'BusinessObjectSyntax.processGroup')) {
      return
    }

    group._containerLevel = depth

    if (!visited) {
      visited = createVisitedSet()
    }

    if (group.id && checkCycle(group.id, visited, 'BusinessObjectSyntax.processGroup')) {
      return
    }
    
    // 使用 titleMap 更新 title（支持多种匹配方式）
    // [FIX 2026-08-04] 用户手动重命名的分组 (标记 _userRenamed) 不被 titleMap 还原，
    //   否则 groupControlTitleMap (原始数据名) 会把面板里的重命名标题覆盖掉。
    let matchedTitle = titleMap[group.id] || titleMap[group.elementCode] || titleMap[group.title]
    if (matchedTitle && !group._userRenamed) {
      group.title = matchedTitle
    }
    
    // [FIX 2026-08-19] 分组禁用: 不再清除 directNodes/containers.
    //   原逻辑在此清空 → BO 从树中消失 → groupedLayout 禁用分支(打平到当前层级)
    //   渲染不到它们 → 后续在顶层"回填" → 子对象跑到父容器之外 (用户反馈:
    //   库存管理禁用后, 子节点应还在采购供应容器内).
    //   保留 directNodes/containers 后, 下方会转成 virtualContainer, groupedLayout
    //   禁用分支把节点打平渲染到父容器层级 (不生成多余子图), 语义符合预期.

    if (group.directNodes && group.directNodes.length > 0) {
      const convertedNodeIds = group.directNodes.map(nodeId => {
        if (typeof nodeId === 'object') {
          return nodeId.id || nodeId.code || nodeId.name || nodeId
        }
        return nodeNameToIdMap.get(nodeId) || nodeCodeToIdMap.get(nodeId) || nodeId
      }).filter(id => id != null)

      if (convertedNodeIds.length > 0) {
        const virtualContainer = {
          id: `${group.id}_direct`,
          name: group.title,
          fullTitle: group.title,
          nodes: convertedNodeIds,
          _groupId: group.id,
          _groupTitle: group.title,
          _isDirectNodesContainer: true,
          _containerLevel: depth + 1
        }

        if (!group.containers) {
          group.containers = []
        }
        group.containers.push(virtualContainer)
        group.directNodes = []
      }
    }

    if (group.containers && group.containers.length > 0) {
      group.containers.forEach((containerRef) => {
        containerRef._containerLevel = depth + 1
        
        // 使用 titleMap 更新容器标题
        const containerMatchedTitle = titleMap[containerRef.id] || titleMap[containerRef.elementCode] || titleMap[containerRef.name]
        if (containerMatchedTitle) {
          containerRef.fullTitle = containerMatchedTitle
        }
        
        if (containerRef.nodes && containerRef.nodes.length > 0) {
          const convertedNodes = containerRef.nodes.map(nodeId => {
            const mermaidId = nodeNameToIdMap.get(nodeId) || nodeCodeToIdMap.get(nodeId)
            if (mermaidId) {
              return mermaidId
            }
            return nodeId
          }).filter(id => id != null)
          
          containerRef.nodes = convertedNodes
          return
        }

        const moduleName = containerRef.name || containerRef.fullTitle
        let matchedNodes = []
        let matchedKey = moduleName

        let moduleGroup = moduleGroups.get(moduleName)

        if (moduleGroup) {
          matchedNodes = moduleGroup.nodes

          if (moduleGroup.info && moduleGroup.info.type === 'subDomain') {
            for (const [key, grp] of moduleGroups.entries()) {
              if (grp.info && grp.info.parent === moduleName) {
                matchedNodes = matchedNodes.concat(grp.nodes)
              }
            }
          }
        }

        if (matchedNodes.length === 0 && containerRef.fullTitle) {
          const parts = containerRef.fullTitle.split(' / ')
          const extractedName = parts.length > 1 ? parts[parts.length - 1] : parts[0]
          moduleGroup = moduleGroups.get(extractedName)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = extractedName
          }
        }

        if (matchedNodes.length === 0 && containerRef.id) {
          moduleGroup = moduleGroups.get(containerRef.id)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = containerRef.id
          }
        }

        if (matchedNodes.length === 0 && containerRef.name) {
          moduleGroup = moduleGroups.get(containerRef.name)
          if (moduleGroup) {
            matchedNodes = moduleGroup.nodes
            matchedKey = containerRef.name
          }
        }

        if (matchedNodes.length === 0) {
          const allMatchingGroups = []
          for (const [key, grp] of moduleGroups.entries()) {
            if (grp.info && grp.info.subDomain === moduleName) {
              allMatchingGroups.push({ key, nodes: grp.nodes })
            }
          }
          if (allMatchingGroups.length > 0) {
            matchedNodes = allMatchingGroups.flatMap(g => g.nodes)
          }
        }

        if (matchedNodes.length > 0 && !usedModules.has(matchedKey)) {
          usedModules.add(matchedKey)
          containerRef.nodes = matchedNodes.map(n => n.id)
        }
      })
    }

    if (group.children && group.children.length > 0) {
      group.children.forEach(childGroup => {
        processGroup(childGroup, visited, depth + 1)
      })
    }
  }

  groups.forEach(group => processGroup(group))

  return groups
}

/**
 * [FOLD 2026-08-05] FR-002: 计算"折叠分组内被隐藏的 BO 节点"的 mermaid id 集合.
 *
 * 折叠分组 (collapsed=true) 渲染为单个聚合节点 (COLLAPSE_<id>), 其子孙 BO 不再渲染.
 * 该方法在 buildVirtualContainers 打平/改写分组树之前调用, 基于原始分组树收集所有
 * 折叠分组的后代 BO 引用 (directNodes 的 BO code / 容器内 nodes), 再映射回业务对象
 * 的 mermaid id, 供后续回填节点 / 上色 / 连线解析跳过.
 *
 * @param {Array} groups 原始分组树 (layoutControlConfig.groups)
 * @param {Array} businessObjectNodes BO 节点数组
 * @param {Map} nodeCodeToIdMap BO code → mermaid id
 * @param {Map} nodeNameToIdMap BO name → mermaid id
 * @param {Array} [disabledBoCodes] 被禁用的 BO 叶业务编码数组 (FR-005, 由 EmbeddedChartView 收集)
 * @returns {Set<string>} 被折叠隐藏的 mermaid 节点 id 集合
 */
/**
 * [FOLD 2026-08-05] FR-005: 从 virtualGroups 树中剪除"被隐藏的 BO 叶"节点 (折叠分组 + 禁用 BO 叶).
 *
 * computeHiddenBoIds 只产出了 hiddenBoIds 集合, 但子图渲染 (generateGroupedLayout →
 * generateContainerCode / generateGroupCode) 直接按 group.containers / group.directNodes
 * 渲染节点, 不检查 hiddenBoIds. 若不剪枝, 被禁用的 BO 叶仍会作为独立节点出现在服务模块
 * subgraph 内 (onlyServiceModules 模板问题: 8 个 BO 仍显示).
 *
 * 该函数在 buildVirtualContainers 打平后的 virtualGroups 上原地剪除:
 *   - 每个容器 (含 _isDirectNodesContainer) 的 nodes 过滤掉 hiddenBoIds 中的 mermaid id
 *   - 剪空后的容器从所属分组移除
 *   - 递归处理 children (嵌套容器)
 *
 * @param {Array} groups virtualGroups (buildVirtualContainers 输出)
 * @param {Set<string>} hiddenBoIds 被隐藏的 BO 的 mermaid id 集合
 */
function pruneHiddenBoNodes(groups, hiddenBoIds) {
  if (!groups || !groups.length || !hiddenBoIds || hiddenBoIds.size === 0) return
  const isHidden = (id) => id != null && hiddenBoIds.has(String(id))

  function pruneGroup(group) {
    if (!group || typeof group !== 'object') return

    // directNodes: 过滤隐藏节点 (buildVirtualContainers 通常已清空, 防御性处理)
    if (group.directNodes && group.directNodes.length) {
      group.directNodes = group.directNodes.filter(n => {
        const id = typeof n === 'object' ? (n.id ?? n.code ?? n.name) : n
        return !isHidden(id)
      })
    }

    // containers: 过滤节点 + 剪除空容器
    if (group.containers && group.containers.length) {
      group.containers = group.containers.filter(c => {
        if (!c || typeof c !== 'object') return true
        if (c.nodes && c.nodes.length) {
          c.nodes = c.nodes.filter(n => {
            const id = typeof n === 'object' ? (n.id ?? n.code ?? n.name) : n
            return !isHidden(id)
          })
        }
        // 嵌套容器先递归剪枝
        if (c.containers && c.containers.length) pruneGroup(c)
        const hasNodes = c.nodes && c.nodes.length > 0
        const hasNested = c.containers && c.containers.length > 0
        return hasNodes || hasNested
      })
    }

    // children: 递归
    if (group.children && group.children.length) {
      group.children.forEach(pruneGroup)
    }
  }

  groups.forEach(pruneGroup)
}

/**
 * [UPLIFT 2026-08-05] 为上提聚合节点 (COLLAPSE_<id>) 着色.
 *
 * 上提分组 (enabled 且无可见子孙 → 渲染为 COLLAPSE_<id> 节点) 默认走 classDef default (灰),
 * 与"上提后该元素有颜色(算是节点不是容器)"语义不符. 该函数遍历分组树, 按当前 colorGroupBy
 * 推导每个上提分组的颜色 (与 BO 节点同源 colorMap), 追加 `style COLLAPSE_<id> ...` 行.
 *
 * 颜色键推导 (与 buildVirtualContainers 前的 colorMap 构建一致):
 * - colorGroupBy='serviceModule' → 分组自身 serviceModuleName/title
 * - colorGroupBy='subDomain'     → 最近祖先 subDomain 标题
 * - colorGroupBy='domain'/默认   → 最近祖先 domain 标题
 *
 * @param {Array} groups 分组树 (virtualGroups, 已带 _uplift 标记)
 * @param {Map} colorMap 分组名 → 颜色 (assignColorsToGroups 产物)
 * @param {string} colorGroupBy 颜色分组模式
 * @param {string} mermaidCode 待追加的 mermaid 代码
 * @param {string} textColor 节点文字色
 * @param {Function} getNodeStyle 生成节点样式字符串
 * @param {Set} centerGroupIds 中心范围分组 id 集合 (含中心范围 BO 的分组)
 * @param {string} centerScopeColor 中心范围颜色
 * @param {boolean} centerScopeHighlight 是否启用中心范围高亮区分
 * @param {Set} fullyCenterGroupIds 完全包含对象范围分组 id 集合 (所有后代 BO 都在中心范围)
 * @returns {Object} { code, colorMap, neutralCollapseIds }
 *   - code: 追加着色后的 mermaid 代码
 *   - colorMap: Map<collapseId, color> 聚合节点颜色映射
 *   - neutralCollapseIds: Set<collapseId> 落入"中性灰"的折叠节点 (折叠层级 > 颜色分组层级,
 *     无法用单一分组色表达, 走 classDef default 灰). 供上层提示"该折叠节点含多分组".
 */
function applyUpliftNodeColors(groups, colorMap, colorGroupBy, mermaidCode, textColor, getNodeStyle, centerGroupIds, centerScopeColor, centerScopeHighlight, fullyCenterGroupIds) {
  // [FIX 2026-08-06] 聚合节点颜色映射 (COLLAPSE_<id> → color):
  //   折叠后连线端点被重映射为聚合节点, nodeColorMap 不含聚合节点 → 连线颜色计算
  //   sourceColor/targetColor 取不到 → 折叠连线变黑. 这里同步产出聚合节点颜色映射,
  //   供连线颜色计算 fallback, 与聚合节点 style 着色逻辑保持一致.
  const collapseColorMap = new Map()
  // [FOLD-COLOR 2026-08-08] 中性灰折叠节点集合 (关系三: 折叠层级 > 颜色分组层级)
  const neutralCollapseIds = new Set()
  function walk(items, ctx) {
    if (!items) return
    for (const g of items) {
      if (!g || typeof g !== 'object') continue
      // [VIS-RESET 2026-08-14] 用户隐藏的分组 (visible=false, 非 ELK 系统自动分组) 跳过整棵子树:
      //   否则 applyUpliftNodeColors 会为它生成 `style COLLAPSE_<id>`, mermaid 会因 style 指令
      //   引用未定义节点 id 而自动创建聚合节点 → 用户反馈: "隐藏采购云后双击供应链云,
      //   出现 COLLAPSE_D_PROC 聚合节点重显". 隐藏分组本就不渲染 (groupedLayout 顶部跳过),
      //   其聚合节点也不该被 style 引用误创建.
      //   ELK 系统自动分组 (无关系/有关系) visible=false 是"无边框但节点渲染"语义, 不属用户隐藏.
      const isSystemAuto = g._elkGroup === 'inner' || g._elkGroup === 'boundary'
      if (g.visible === false && !isSystemAuto) {
        continue
      }
      const nextCtx = { ...ctx }
      if (g.groupType === 'domain') nextCtx.domain = g.title
      else if (g.groupType === 'subDomain') nextCtx.subDomain = g.title

      if (g._uplift === true) {
        const safeId = String(g.id).replace(/[^\w\u4e00-\u9fff]/g, '_')
        const collapseId = `COLLAPSE_${safeId}`
        // [CUSTOM-COLOR 2026-08-19] 用户自定义分组的聚合节点用面板配置色 (group.style),
        //   不被 colorGroupBy/中心范围覆盖: 用户把自定义分组拖入某领域/子领域下后, 其折叠
        //   聚合节点仍应保持面板设置色 (如黄色), 而非继承所属领域的分组色 (用户反馈"变蓝").
        //   groupedLayout 已为自定义分组聚合节点写 style 行, 此处再用自定义色写 style 并同步
        //   collapseColorMap (供折叠连线 fallback), 然后跳过下方 colorGroupBy 取色分支.
        const isUserCustomGroup = g.groupType === 'custom'
          && !(g._elkGroup === 'inner' || g._elkGroup === 'boundary')
        if (isUserCustomGroup) {
          const customFill = g.style && g.style.fill
          if (customFill) {
            mermaidCode += `  style ${collapseId} ${getNodeStyle(customFill, textColor)}\n`
            collapseColorMap.set(collapseId, customFill)
          }
          continue
        }
        // [FIX 2026-08-06] 折叠聚合节点: 中心范围分组保持 centerScopeColor,
        //   与展开态中心范围内 BO 节点 (centerScopeColor) 的颜色一致.
        // [PARTIAL-CENTER 2026-08-15] 部分包含对象范围 (中心分组但非完全包含, 范围内+范围外混合)
        //   → 中性灰 (不写 style, 走 classDef default), 与增量路径 updateCollapseNodeColors 同规则.
        //   不入 neutralCollapseIds (该集合用于"折叠层级 > 分组层级"的中性提示, 语义不同).
        const isCenterGroup = centerScopeHighlight !== false && centerGroupIds && centerGroupIds.has(g.id)
        if (isCenterGroup && (!fullyCenterGroupIds || !fullyCenterGroupIds.has(g.id))) {
          continue
        }
        if (isCenterGroup) {
          mermaidCode += `  style ${collapseId} ${getNodeStyle(centerScopeColor, textColor)}\n`
          collapseColorMap.set(collapseId, centerScopeColor)
        } else {
          // [FOLD-COLOR 2026-08-08] 折叠节点取色遵循层级关系 (见函数头注释):
          //   - 关系一 (折叠层级 == 分组层级): 分组自身 key (如折叠 SM + 按 SM 分组)
          //   - 关系二 (折叠层级 < 分组层级, 折叠更细): 继承上层分组 key (如折叠 SM + 按 domain)
          //   - 关系三 (折叠层级 > 分组层级, 折叠更粗): 取不到单一分组 key → 中性灰
          // [FOLD-COLOR 2026-08-12] 关系三改为显式层级判断 (旧实现依赖 colorMap.get(key)
          //   命中与否, 同码同名场景误命中: 子领域"内部交易"=ITTF 与服务模块"内部交易"同名,
          //   key=g.title → 命中服务模块分组色 → 显示彩色而非中性)。
          //   层级数值: domain=0, subDomain=1, serviceModule=2 (见 services/expandLevel.js groupTypeLevel)
          const levelOf = (t) => (t === 'domain' ? 0 : t === 'subDomain' ? 1 : t === 'serviceModule' ? 2 : -1)
          const foldLevel = levelOf(g.groupType)
          const groupLevel = levelOf(colorGroupBy)
          if (foldLevel >= 0 && groupLevel >= 0 && foldLevel < groupLevel) {
            neutralCollapseIds.add(collapseId)
            continue
          }
          let key
          if (colorGroupBy === 'serviceModule') key = g.serviceModuleName || g.title
          else if (colorGroupBy === 'subDomain') key = g.subDomain || nextCtx.subDomain
          else key = g.domain || nextCtx.domain
          const color = key ? colorMap.get(key) : undefined
          if (color) {
            mermaidCode += `  style ${collapseId} ${getNodeStyle(color, textColor)}\n`
            collapseColorMap.set(collapseId, color)
          } else {
            // [FOLD-COLOR 2026-08-08] 关系三: 折叠层级 > 颜色分组层级, 无法用单一分组色表达,
            //   回退 classDef default (灰), 并收集供上层弹"含多分组"提示.
            neutralCollapseIds.add(collapseId)
          }
        }
      }

      walk(g.children, nextCtx)
      walk(g.containers, nextCtx)
    }
  }
  walk(groups, {})
  return { code: mermaidCode, colorMap: collapseColorMap, neutralCollapseIds }
}

function computeHiddenBoIds(groups, businessObjectNodes, nodeCodeToIdMap, nodeNameToIdMap, disabledBoCodes) {
  const hiddenIds = new Set()

  // 收集折叠分组下所有后代的引用 (code/name/id)
  const hiddenRefs = new Set()
  function addRef(n) {
    if (n == null) return
    if (typeof n === 'object') {
      if (n.code != null) hiddenRefs.add(String(n.code))
      if (n.name != null) hiddenRefs.add(String(n.name))
      if (n.id != null) hiddenRefs.add(String(n.id))
    } else {
      hiddenRefs.add(String(n))
    }
  }
  if (groups && groups.length) {
  function collectDescendantRefs(group) {
    if (!group) return
    if (group.directNodes && group.directNodes.length) {
      group.directNodes.forEach(addRef)
    }
    if (group.containers && group.containers.length) {
      group.containers.forEach(c => {
        if (!c || typeof c !== 'object') return
        if (c.nodes && c.nodes.length) c.nodes.forEach(addRef)
        if (c.elementRef?.code != null) hiddenRefs.add(String(c.elementRef.code))
        if (c.elementCode != null) hiddenRefs.add(String(c.elementCode))
        if (c.name != null) hiddenRefs.add(String(c.name))
        if (c.containers && c.containers.length) {
          c.containers.forEach(nc => {
            if (nc && typeof nc === 'object' && nc.nodes && nc.nodes.length) nc.nodes.forEach(addRef)
          })
        }
      })
    }
    if (group.children && group.children.length) {
      group.children.forEach(collectDescendantRefs)
    }
  }
  // [UPLIFT 2026-08-05] 上提推导: enabled 且无可见子孙的分组 → 聚合节点, 其后代 BO 隐藏.
  const uplift = computeUplift(groups)
  function walk(groupList) {
    if (!groupList || !groupList.length) return
    for (const group of groupList) {
      if (!group) continue
      if (uplift.has(group.id)) {
        collectDescendantRefs(group)
        continue // 后代已全部收集, 无需再递归
      }
      if (group.children && group.children.length) walk(group.children)
    }
  }
  walk(groups)

  // [FOLD 2026-08-05] FR-005: 被禁用的 BO 叶容器 (isVirtual=true 且 enabled=false) 也应隐藏,
  //   用于 "onlyServiceModules" 等视图模板 (禁用所有 BO 叶). 折叠收集的是"整组隐藏",
  //   这里收集的是"单个 BO 叶隐藏". (手动禁用 BO 叶 = 隐藏, 而非外提.)
  function walkDisabledBoLeaf(groupList) {
    if (!groupList || !groupList.length) return
    for (const group of groupList) {
      if (!group) continue
      if (group.containers && group.containers.length) {
        group.containers.forEach(c => {
          if (c && typeof c === 'object' && c.isVirtual === true && c.enabled === false) {
            if (c.nodes && c.nodes.length) c.nodes.forEach(addRef)
            if (c.elementRef?.code != null) hiddenRefs.add(String(c.elementRef.code))
            if (c.elementCode != null) hiddenRefs.add(String(c.elementCode))
          }
        })
      }
      if (group.children && group.children.length) walkDisabledBoLeaf(group.children)
    }
  }
  walkDisabledBoLeaf(groups)
  }

  // [FOLD 2026-08-05] FR-005: EmbeddedChartView 显式收集的"被禁用 BO 叶"业务编码.
  //   部分数据路径的 BO 叶在面板树中表示为 isVirtual 容器, 但 mergedGroups 里是 directNodes,
  //   无法在 walkDisabledBoLeaf 中按容器匹配, 故直接并入 hiddenRefs.
  //   注意: 该处理必须在 groups 空守卫之外, 因为 onlyServiceModules 模板可能清空所有分组树容器.
  if (disabledBoCodes && disabledBoCodes.length) {
    disabledBoCodes.forEach(c => { if (c != null) hiddenRefs.add(String(c)) })
  }

  if (hiddenRefs.size === 0) return hiddenIds

  businessObjectNodes.forEach(node => {
    const code = node.code != null ? String(node.code) : null
    const name = (node.originalName || node.name) != null ? String(node.originalName || node.name) : null
    const matched = (code && hiddenRefs.has(code)) || (name && hiddenRefs.has(name))
    if (matched) {
      const id = (code && nodeCodeToIdMap.get(code)) || (name && nodeNameToIdMap.get(name))
      if (id) hiddenIds.add(id)
    }
  })
  return hiddenIds
}

export function useBusinessObjectSyntax() {
  const { getContainerStyle, getLinkStyle, getNodeStyle, generateClassDefs } = useBlockDiagramStyle()
  const { preCalculateNodeSizes } = useBlockDiagramSyntax()

  const generateMermaidCode = (data, relationDescriptions, layoutEngine = 'dagre', layoutType = 'grouped', layoutControlConfig = null) => {
    if (!data || !data.nodes || !data.links) {
      return 'graph TD\n  A[No Data]'
    }

    preCalculateNodeSizes(data, DIAGRAM_TYPES.BUSINESS_OBJECT)

    const effectiveLayoutControlConfig = layoutControlConfig

    const overallDirection = effectiveLayoutControlConfig?.overallDirection || 'TB'

    // ELK布局使用与配置一致的方向，不再反向    // ELK的elk.direction配置会控制实际布局方向
    let actualDirection = overallDirection

    let graphKeyword
    let elkInitDirective = ''
    if (layoutEngine === 'elk') {
      graphKeyword = `flowchart-elk ${actualDirection}`
      // ELK配置通过mermaid.initialize传递，不需要在代码中重复配置      elkInitDirective = ''
    } else {
      graphKeyword = `flowchart ${actualDirection}`
    }
    
    let mermaidCode = elkInitDirective + graphKeyword + '\n'
    const nodeCodeToIdMap = new Map()
    const nodeNameToIdMap = new Map()
    const nodeIdToCodeMap = new Map()
    // [v33 关键修复] nodeId → node name 映射, 用于 tooltip 显示源/目标节点名
    // 之前 relationDescriptions 存的是 link.sourceName (可能 undefined),
    // 导致 tooltip 中 "源 → 目标" 节点名为空
    const nodeIdToNameMap = new Map()
    let nodeId = 1

    const objectToModuleMap = new Map()
    
    // 首先从顶层businessObjects 数组获取服务模块信息
    const boServiceModuleMap = new Map()
    if (data.businessObjects) {
      data.businessObjects.forEach(bo => {
        if (bo.code || bo.name) {
          boServiceModuleMap.set(bo.code || bo.name, {
            serviceModule: bo.serviceModule,
            serviceModuleName: bo.serviceModuleName
          })
        }
      })
    }
    
    if (data.domainProducts) {
      data.domainProducts.forEach(domain => {
        if (domain.businessObjects) {
          domain.businessObjects.forEach(bo => {
            const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
            objectToModuleMap.set(bo.code || bo.name, {
              type: 'domain',
              name: domain.name,
              code: domain.code,
              serviceModule: smInfo.serviceModule || bo.serviceModule,
              serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
            })
          })
        }
        if (domain.modules) {
          domain.modules.forEach(module => {
            if (module.businessObjects) {
              module.businessObjects.forEach(bo => {
                const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
                objectToModuleMap.set(bo.code || bo.name, {
                  type: 'module',
                  name: module.name,
                  code: module.code,
                  parent: domain.name,
                  serviceModule: smInfo.serviceModule || bo.serviceModule,
                  serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
                })
              })
            }
            if (module.submodules) {
              module.submodules.forEach(submodule => {
                if (submodule.businessObjects) {
                  submodule.businessObjects.forEach(bo => {
                    const smInfo = boServiceModuleMap.get(bo.code || bo.name) || {}
                    objectToModuleMap.set(bo.code || bo.name, {
                      type: 'submodule',
                      name: submodule.name,
                      code: submodule.code,
                      parent: module.name,
                      grandparent: domain.name,
                      serviceModule: smInfo.serviceModule || bo.serviceModule,
                      serviceModuleName: smInfo.serviceModuleName || bo.serviceModuleName
                    })
                  })
                }
              })
            }
          })
        }
      })
    }

    const moduleGroups = new Map()

    const businessObjectNodes = data.nodes.filter(node => node.category === 'object')

    businessObjectNodes.forEach(node => {
      const id = `N${nodeId++}`
      const originalName = node.originalName || node.name
      const nodeCode = node.code

      if (nodeCode) {
        nodeCodeToIdMap.set(nodeCode, id)
      }
      nodeNameToIdMap.set(originalName, id)
      nodeIdToCodeMap.set(id, nodeCode || originalName)
      // [v33 关键修复] 记录 id → 节点名, 用于 tooltip 回查
      nodeIdToNameMap.set(id, originalName)

      const moduleInfo = objectToModuleMap.get(nodeCode) || objectToModuleMap.get(originalName)

      if (moduleInfo) {
        let groupKey, groupInfo
        if (moduleInfo.type === 'submodule') {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'submodule',
            name: moduleInfo.name,
            parent: moduleInfo.parent,
            grandparent: moduleInfo.grandparent,
            domain: moduleInfo.grandparent,
            subDomain: moduleInfo.parent,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        } else if (moduleInfo.type === 'module') {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'module',
            name: moduleInfo.name,
            parent: moduleInfo.parent,
            domain: moduleInfo.parent,
            subDomain: moduleInfo.name,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        } else {
          groupKey = moduleInfo.name
          groupInfo = {
            type: 'domain',
            name: moduleInfo.name,
            domain: moduleInfo.name,
            subDomain: moduleInfo.name,
            serviceModule: moduleInfo.serviceModule,
            serviceModuleName: moduleInfo.serviceModuleName
          }
        }

        if (!moduleGroups.has(groupKey)) {
          moduleGroups.set(groupKey, {
            info: groupInfo,
            nodes: []
          })
        }
        moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
      } else {
        if (node.subDomain) {
          const groupKey = node.subDomain
          if (!moduleGroups.has(groupKey)) {
            moduleGroups.set(groupKey, {
              info: { name: groupKey, type: 'subDomain', domain: node.domain || groupKey, subDomain: groupKey },
              nodes: []
            })
          }
          moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
        } else {
          const groupKey = '其他'
          if (!moduleGroups.has(groupKey)) {
            moduleGroups.set(groupKey, {
              info: { name: '其他', type: 'unknown', domain: '其他', subDomain: '其他' },
              nodes: []
            })
          }
          moduleGroups.get(groupKey).nodes.push({ id, originalName, nodeCode, code: nodeCode, isCenter: node.isCenter })
        }
      }
    })

    const colorGroupBy = data.colorGroupBy || 'domain'

    const colors = getColors(data.colorScheme)

    const uniqueGroups = new Set()
    // [FIX 2026-07-31 v3] uniqueGroups 按 BO 自身字段去重 (而非 moduleGroup 的 info)
    //   原因: moduleGroup 按 domain/submodule 维度聚合, 同 group 可能含多个不同 serviceModule 的 BO。
    //   修复: 直接遍历 businessObjectNodes 用每个 BO 自身的字段算 groupKey。
    businessObjectNodes.forEach(node => {
      const nodeCode = node.code || node.originalName || node.name
      const selfModule = objectToModuleMap.get(nodeCode) || {}
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = selfModule.serviceModuleName || selfModule.serviceModule
      } else if (colorGroupBy === 'subDomain') {
        groupKey = selfModule.subDomain || node.subDomain
      } else {
        groupKey = selfModule.domain || node.domain
      }
      if (groupKey) uniqueGroups.add(groupKey)
    })

    const colorMap = assignColorsToGroups(new Set(uniqueGroups), colors, data.customColors || {})

    const subDomainGroups = new Map()
    moduleGroups.forEach((group, groupName) => {
      const subDomain = group.info.subDomain || '其他'
      if (!subDomainGroups.has(subDomain)) {
        subDomainGroups.set(subDomain, [])
      }
      subDomainGroups.get(subDomain).push({ groupName, group })
    })

    const sortedSubDomains = Array.from(subDomainGroups.keys()).sort((a, b) => {
      return a.localeCompare(b, 'zh-CN')
    })

    const sortedGroups = new Map()
    sortedSubDomains.forEach(subDomain => {
      const groups = subDomainGroups.get(subDomain)
      groups.sort((a, b) => a.groupName.localeCompare(b.groupName, 'zh-CN'))
      groups.forEach(({ groupName, group }) => {
        sortedGroups.set(groupName, group)
      })
    })

    const optimizedGroups = sortedGroups

    const nodeColorMap = new Map()
    const centerNodeIds = new Set()  // [FIX 2026-08-02 v5] 中心范围节点 id 集合 (用于 centerScopeColor 填色区分)
    const centerScopeBoCodes = data.centerScope || []
    const centerScopeHighlight = data.centerScopeHighlight !== false  // 默认为true
    const centerScopeColor = data.centerScopeColor === 'gray' ? '#808080' : (data.centerScopeColor || '#808080')

    // [FIX 2026-08-06] 中心范围分组 id 集合: 折叠/上提聚合节点着色时保持 centerScopeColor.
    //   基于原始分组树 (buildVirtualContainers 改造前) 收集每个分组的后代 BO 编码,
    //   与 data.centerScope 求交集判定该分组是否属于中心范围.
    const centerScopeCodeSet = new Set(centerScopeBoCodes)
    const centerGroupIds = new Set()
    // [PARTIAL-CENTER 2026-08-15] 完全包含对象范围分组 id 集合: 该分组所有后代 BO 编码都在
    //   centerScope 中. 与 centerGroupIds (任一后代在范围) 配合区分折叠节点着色:
    //   fully → centerScopeColor; 部分包含 (范围内+范围外混合) → 中性灰.
    const fullyCenterGroupIds = new Set()
    // [FIX 2026-08-06] 中心范围聚合节点编码集合 (COLLAPSE_<id>): 折叠后连线端点被重映射为
    //   COLLAPSE_<id>, 不在 centerScopeBoCodes 中, 需用该集合判定中心范围, 避免折叠连线变黑.
    const centerCollapseIds = new Set()
    function collectDescendantBoCodes(group, out) {
      if (!group) return
      if (group.directNodes && group.directNodes.length) {
        group.directNodes.forEach(n => {
          if (n == null) return
          out.add(String(typeof n === 'object' ? (n.code ?? n.id ?? n.name) : n))
        })
      }
      if (group.containers && group.containers.length) {
        group.containers.forEach(c => {
          if (!c || typeof c !== 'object') return
          if (c.nodes && c.nodes.length) c.nodes.forEach(n => out.add(String(typeof n === 'object' ? (n.code ?? n.id ?? n.name) : n)))
          if (c.elementRef?.code != null) out.add(String(c.elementRef.code))
          if (c.elementCode != null) out.add(String(c.elementCode))
          if (c.containers && c.containers.length) {
            c.containers.forEach(nc => { if (nc && typeof nc === 'object' && nc.nodes && nc.nodes.length) nc.nodes.forEach(n => out.add(String(typeof n === 'object' ? (n.code ?? n.id ?? n.name) : n))) })
          }
        })
      }
      if (group.children && group.children.length) group.children.forEach(g => collectDescendantBoCodes(g, out))
    }
    function markCenterGroups(groups) {
      if (!groups || !groups.length) return
      for (const g of groups) {
        if (!g) continue
        const codes = new Set()
        collectDescendantBoCodes(g, codes)
        // [PARTIAL-CENTER 2026-08-15] 遍历全部编码同时判定 any/all (原实现命中首个中心即 break).
        let anyCenter = false
        let allCenter = codes.size > 0
        for (const c of codes) {
          if (centerScopeCodeSet.has(c)) anyCenter = true
          else allCenter = false
        }
        if (anyCenter) { centerGroupIds.add(g.id); centerCollapseIds.add(`COLLAPSE_${sanitizeId(g.id)}`) }
        if (allCenter) fullyCenterGroupIds.add(g.id)
        markCenterGroups(g.children)
      }
    }
    markCenterGroups(effectiveLayoutControlConfig?.groups || [])

    optimizedGroups.forEach((group) => {
      // [FIX 2026-07-31 v3] 颜色按 BO 自身字段分组, 而非 moduleGroup 的 info
      //   之前用 group.info.serviceModuleName 作为 groupKey, 但 moduleGroup 是按 domain/submodule
      //   维度聚合的（多个不同 serviceModule 的 BO 会进同一个 moduleGroup）, 导致 group.info
      //   只记录首个 BO 的 serviceModuleName, 后续 BO 全被染成同色。
      //   修复: 用每个 node 自身的 serviceModuleName/serviceModule/subDomain/domain 算 groupKey。
      group.nodes.forEach(node => {
        const nodeCode = node.code || node.name
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          // 优先用 BO 自身的 serviceModuleName, fallback 到 group.info
          const selfModule = objectToModuleMap.get(nodeCode) || objectToModuleMap.get(node.originalName)
          groupKey = selfModule?.serviceModuleName || selfModule?.serviceModule || group.info.serviceModuleName || group.info.serviceModule || group.info.name
        } else if (colorGroupBy === 'subDomain') {
          groupKey = group.info.subDomain
        } else {
          groupKey = group.info.domain
        }
        const groupColor = colorMap.get(groupKey)
        const defaultColor = colors[0]
        // [FIX 2026-08-02 v5] 回到原方案: nodeColorMap 统一记分组色 (中心节点区分在 style 生成时用 centerScopeColor)
        nodeColorMap.set(node.id, groupColor || defaultColor)
        if (centerScopeHighlight && centerScopeBoCodes.includes(nodeCode)) {
          centerNodeIds.add(node.id)
        }
      })
    })

    // [FIX 2026-08-13] 折叠降阶失效根因修复: 进入生成流程前深拷贝 groups 为工作副本.
    //   污染链: buildVirtualContainers 把 group.directNodes 的 BO code 原地改写成 mermaid id
    //   (N1/N2) 并清空 directNodes; pruneHiddenBoNodes 再原地剪除折叠/禁用 BO 子孙;
    //   markUplift / applyContainerSorting 亦原地写. 而 MermaidComponent 的
    //   effectiveLayoutControlConfig 是有缓存的 computed → 上述原地改写会污染缓存对象,
    //   导致第二次 generateMermaidCode 调用 (ELK 失败回退 dagre / watch 触发重渲染) 复用
    //   被污染的分组树 → computeHiddenBoIds 按业务 code/name 匹配不到 → hiddenBoIds 为空
    //   → 折叠不降阶、全部 BO 全量渲染 (44 节点而非 3 聚合节点).
    //   修复: 让 buildVirtualContainers 及后续所有原地修改只作用于副本, 源缓存保持纯净,
    //   每次调用都能正确推导隐藏 BO, 折叠真正缩减喂给 ELK 的 mermaid 源码规模.
    const workingGroups = JSON.parse(JSON.stringify(effectiveLayoutControlConfig?.groups || []))

    // [FOLD 2026-08-05] FR-002/FR-005: 折叠分组 + 被禁用 BO 叶 → 隐藏的 BO 节点 id 集合.
    //   在 buildVirtualContainers 打平/转换分组前, 先用原始分组树收集
    //   (基于 code/name → 原始业务对象节点), 供后续回填节点 / 上色 / 连线解析跳过.
    //   (必须在 buildVirtualContainers 之前, 否则容器节点已被改写为 mermaid id,
    //   无法再按业务 code/name 匹配.)
    //   提升到分支外: 两个渲染路径 (groupedLayout 与 SG 兜底路径) 都要过滤隐藏 BO 叶.
    const hiddenBoIds = computeHiddenBoIds(
      workingGroups,
      businessObjectNodes,
      nodeCodeToIdMap,
      nodeNameToIdMap,
      effectiveLayoutControlConfig?.disabledBoCodes || []
    )

    if (effectiveLayoutControlConfig?.enabled && workingGroups.length > 0) {
      // [FIX 2026-08-13] 重映射快照基于工作副本: workingGroups 是纯净的原始分组树 (尚未被
      //   buildVirtualContainers 改写), 保留业务 BO code 引用, 供 remapLinksToVisibleAncestors
      //   把折叠连线端点重映射到聚合节点 (COLLAPSE_<id>).
      const remapGroups = JSON.parse(JSON.stringify(workingGroups))
      const titleMap = data?.groupControlTitleMap || {}
      const virtualGroups = buildVirtualContainers(
        workingGroups,
        moduleGroups,
        businessObjectNodes,
        nodeNameToIdMap,
        nodeCodeToIdMap,
        titleMap
      )

      // [FOLD 2026-08-05] FR-005: 剪除被隐藏的 BO 叶 (折叠分组 + 禁用 BO 叶).
      //   必须在 collectContainers/routeLayout 之前, 否则子图渲染仍会渲染这些节点.
      pruneHiddenBoNodes(virtualGroups, hiddenBoIds)
      
      DataFlowLogger.BusinessObjectSyntax.buildVirtualContainers(
        virtualGroups,
        virtualGroups
      )

      const allContainers = []
      virtualGroups.forEach(g => collectContainers(g, allContainers))
      
      const sortingStrategy = effectiveLayoutControlConfig?.containerSortingStrategy || 'combined'
      
      if (sortingStrategy !== 'none' && allContainers.length > 1) {
        const processedLinks = []
        data.links.forEach(link => {
          let sourceId = null
          let targetId = null

          if (link.sourceCode) {
            sourceId = nodeCodeToIdMap.get(link.sourceCode)
          }
          if (link.targetCode) {
            targetId = nodeCodeToIdMap.get(link.targetCode)
          }

          if (!sourceId) {
            sourceId = nodeNameToIdMap.get(link.sourceName)
          }
          if (!targetId) {
            targetId = nodeNameToIdMap.get(link.targetName)
          }

          if (sourceId && targetId) {
            processedLinks.push({ source: sourceId, target: targetId })
          }
        })
        
        const sortedContainers = sortVirtualContainers(allContainers, processedLinks, sortingStrategy)
        
        function applyContainerSorting(groups, sortedContainers) {
          const sortedIds = new Set(sortedContainers.map(c => c.id))
          
          groups.forEach(group => {
            if (group.containers && group.containers.length > 0) {
              const sortedGroupContainers = []
              sortedContainers.forEach(sortedContainer => {
                const found = group.containers.find(c => c.id === sortedContainer.id)
                if (found) {
                  sortedGroupContainers.push(found)
                }
              })
              group.containers.forEach(c => {
                if (!sortedIds.has(c.id)) {
                  sortedGroupContainers.push(c)
                }
              })
              group.containers = sortedGroupContainers
            }
            
            if (group.children && group.children.length > 0) {
              applyContainerSorting(group.children, sortedContainers)
            }
          })
        }
        
        applyContainerSorting(virtualGroups, sortedContainers)
      }

      // [UPLIFT 2026-08-05] "仅服务模块"模板: BO 叶全禁用 → allContainers 为空, 但
      //   groups 仍含启用的服务模块分组. 需按 groups (而非 allContainers) 决定是否走 groupedLayout,
      //   否则服务模块 (enabled 且无可见子孙) 会落入 SG 空容器兜底 (只显示标题, 无节点).
      //   nodeMap/processedLinks 基于 businessObjectNodes/data.links, 不依赖 allContainers,
      //   routeLayout 收到 virtualGroups, 空容器下仍能按 uplift 上提渲染服务模块.
      if (allContainers.length > 0 || workingGroups.length > 0) {
        const nodeMap = new Map()
        
        businessObjectNodes.forEach(node => {
          const key = node.originalName || node.name
          const id = nodeNameToIdMap.get(key)
          const nodeData = {
            id: id,
            name: node.originalName || node.name,
            code: node.code
          }
          if (id) {
            nodeMap.set(id, nodeData)
          }
        })

        moduleGroups.forEach((group, groupKey) => {
          group.nodes.forEach(node => {
            if (node.id && !nodeMap.has(node.id)) {
              nodeMap.set(node.id, {
                id: node.id,
                name: node.name || node.originalName || node.id,
                code: node.code || node.nodeCode
              })
            }
          })
        })

        const definedNodes = new Set()

        // 提前处理 links 数据，用于ELK 自动分组
        const processedLinks = []
        data.links.forEach(link => {
          let sourceId = null
          let targetId = null

          if (link.sourceCode) {
            sourceId = nodeCodeToIdMap.get(link.sourceCode)
          }
          if (link.targetCode) {
            targetId = nodeCodeToIdMap.get(link.targetCode)
          }

          if (!sourceId) {
            sourceId = nodeNameToIdMap.get(link.sourceName)
          }
          if (!targetId) {
            targetId = nodeNameToIdMap.get(link.targetName)
          }

          if (sourceId && targetId) {
            processedLinks.push({ source: sourceId, target: targetId })
          }
        })

        const layoutCode = routeLayout(allContainers, {
          layoutType: 'grouped',
          layoutEngine,
          nodeMap,
          definedNodes,
          layoutControlConfig: {
            ...effectiveLayoutControlConfig,
            groups: virtualGroups
          },
          overallDirection: actualDirection,
          links: processedLinks
        })

        // [FOLD 2026-08-05] 折叠分组内被隐藏的 BO 节点 id 集合已在 buildVirtualContainers 前
        //   计算 (见上方 computeHiddenBoIds). 折叠后 BO 叶不再回填为 standalone 节点、不再上色,
        //   连线端点已由 remapLinksToVisibleAncestors 重映射到聚合节点.
        if (layoutCode) {
          mermaidCode += layoutCode

          businessObjectNodes.forEach(node => {
            const key = node.originalName || node.name
            const id = nodeNameToIdMap.get(key)
            if (id && !definedNodes.has(id) && !hiddenBoIds.has(id)) {
              // [TEMPLATE 2026-08-11] BO 标签统一走模板 (名称\n编码 两行)
              const displayText = businessObjectLabel(node)
              mermaidCode += `  ${id}["${displayText}"]:::node\n`
              definedNodes.add(id)
            }
          })
        } else {
          virtualGroups.forEach(group => {
            mermaidCode += generateGroupMermaid(group, nodeMap, definedNodes, actualDirection)
          })
        }

        const nodeColorMappings = []
        const textColor = data.nodeTextColor || '#000000'
        businessObjectNodes.forEach(node => {
          // 优先使用 code 查找 id，避免同名不同编码的对象冲突
          const nodeCode = node.code
          const id = nodeCode ? nodeCodeToIdMap.get(nodeCode) : nodeNameToIdMap.get(node.originalName || node.name)
          if (hiddenBoIds.has(id)) return
          const nodeColor = nodeColorMap.get(id)
          const isCenter = centerNodeIds.has(id)
          // [FIX 2026-08-02 v5] 回到原方案: 中心范围节点 fill = centerScopeColor (指定颜色), 默认边框
          const finalColor = isCenter ? centerScopeColor : (nodeColor || '#FF9AA2')
          mermaidCode += `  style ${id} ${getNodeStyle(finalColor, textColor)}\n`
          nodeColorMappings.push({ nodeId: id, color: nodeColor, nodeCode: node.code, nodeName: node.originalName || node.name, isCenter })
        })

        // [UPLIFT 2026-08-05] 上提聚合节点着色: COLLAPSE_<id> 默认灰, 按 colorGroupBy 推导分组色.
        //   先确保 _uplift 已标记 (generateGroupedLayout 内 markUplift 可能作用于内部副本),
        //   再为每个上提分组追加 style 行, 使其成为"有颜色的节点"而非灰标签.
        markUplift(virtualGroups)
        const upliftStyleResult = applyUpliftNodeColors(virtualGroups, colorMap, colorGroupBy, mermaidCode, textColor, getNodeStyle, centerGroupIds, centerScopeColor, centerScopeHighlight, fullyCenterGroupIds)
        mermaidCode = upliftStyleResult.code
        // [FIX 2026-08-06] 聚合节点颜色映射: 折叠连线端点 (COLLAPSE_<id>) 用它取色,
        //   避免折叠后连线因 nodeColorMap 查不到聚合节点而变黑.
        const collapseColorMap = upliftStyleResult.colorMap

        // [FIX 2026-08-05] 折叠上提后连线必须重映射到聚合节点 (COLLAPSE_<id>)。
        //   remapLinksToVisibleAncestors 之前定义了却未接入主流程, 导致折叠后连线端点
        //   仍指向被隐藏的 BO → 被下方 filter 当作"隐藏节点连线"丢弃 (折叠后连线消失 bug).
        //   现基于原始分组树对上提分组的子孙端点做最近可见祖先重映射。
        const remappedLinks = remapLinksToVisibleAncestors(
          data.links,
          remapGroups,
          data.domainProducts
        )

        // [FUSE 2026-08-06] 关系连线融合: 折叠后多条 BO 关系重映射到同一"可见节点对"
        //   产生重复连线, 且方向相反的对应合并为双向 (A<->B). 融合后再喂给渲染/诊断.
        const fusedRemappedLinks = fuseLinks(remappedLinks)

        // [DIAG 2026-08-06] 折叠连线编码排查探针 (dev-only, core/linkDiagnostics.js):
        //   一次性捕获 前序模型(domainProducts) → 布局分组树(remapGroups) → 重映射连线(remapped)
        //   三段编码快照, 供 E2E/脚本核对"领域/子领域/服务模块编码是否在折叠后正确携带".
        recordLinkDiag({
          domainProducts: data.domainProducts,
          remapGroups,
          links: data.links,
          remappedLinks: fusedRemappedLinks
        })

        const businessObjectLinks = fusedRemappedLinks.filter(link => {
          // [v1.1.15 修复] 跨域关系连线过滤逻辑与下方 sourceId/targetId 解析保持一致
          //   旧逻辑: filter 用 && (AND) 要求 sourceCode+targetCode 同时在 map
          //           但下方解析用 || (OR) code 优先 fallback name
          //   结果: 跨域 link 的 source 在 nodeCodeToIdMap, target 只在 nodeNameToIdMap
          //         时, filter 漏掉 (因为 targetCode 不在 nodeCodeToIdMap)
          //   修复: filter 也用 OR-after-AND, 任一 code/name 在 map 就接受
          //   [FIX 2026-08-05] COLLAPSE_<id> 聚合端点不在 nodeCodeToIdMap/nodeNameToIdMap 中
          //   (重映射自上提分组), 必须视为 found, 否则折叠后连线被丢弃。
          const srcIsCollapse = String(link.sourceCode || '').startsWith('COLLAPSE_')
          const tgtIsCollapse = String(link.targetCode || '').startsWith('COLLAPSE_')
          const sourceFound = srcIsCollapse ||
                              ((link.sourceCode && nodeCodeToIdMap.has(link.sourceCode)) ||
                               (link.sourceName && nodeNameToIdMap.has(link.sourceName)))
          const targetFound = tgtIsCollapse ||
                              ((link.targetCode && nodeCodeToIdMap.has(link.targetCode)) ||
                               (link.targetName && nodeNameToIdMap.has(link.targetName)))

          // [FOLD 2026-08-05] FR-005: 过滤掉两端连到"被隐藏 BO 叶"的连线 (禁用 BO 叶时其节点不渲染,
          //   连线必须一并丢弃, 否则 mermaid 会自动补建被隐藏的节点). 注意排除 COLLAPSE_ 聚合端点
          //   (折叠分组连线已被 remapLinksToVisibleAncestors 重映射到聚合节点, 必须保留).
          const filterSourceId = (link.sourceCode && nodeCodeToIdMap.get(link.sourceCode)) ||
                                 (link.sourceName && nodeNameToIdMap.get(link.sourceName))
          const filterTargetId = (link.targetCode && nodeCodeToIdMap.get(link.targetCode)) ||
                                 (link.targetName && nodeNameToIdMap.get(link.targetName))
          const sourceHidden = !srcIsCollapse && hiddenBoIds.has(filterSourceId)
          const targetHidden = !tgtIsCollapse && hiddenBoIds.has(filterTargetId)

          return sourceFound && targetFound && !sourceHidden && !targetHidden
        })

        const linkColorMappings = []
        businessObjectLinks.forEach((link, index) => {
          let sourceId = null
          let targetId = null

          // [FOLD 2026-08-05] 连线端点可能已被 remapLinksToVisibleAncestors 重映射为
          //   折叠聚合节点编码 (COLLAPSE_<id>). 该编码不在 nodeCodeToIdMap 中, 若按正常
          //   code→id 解析会落空并回退到 sourceName (原始 BO 名) → 重新指向被隐藏的 BO,
          //   导致折叠后连线仍连到不存在的节点. 故 COLLAPSE_<id> 端点直接作为 mermaid 节点 id.
          if (link.sourceCode) {
            sourceId = String(link.sourceCode).startsWith('COLLAPSE_') ? String(link.sourceCode) : nodeCodeToIdMap.get(link.sourceCode)
          }
          if (link.targetCode) {
            targetId = String(link.targetCode).startsWith('COLLAPSE_') ? String(link.targetCode) : nodeCodeToIdMap.get(link.targetCode)
          }

          if (!sourceId) {
            sourceId = nodeNameToIdMap.get(link.sourceName)
          }
          if (!targetId) {
            targetId = nodeNameToIdMap.get(link.targetName)
          }

          if (sourceId && targetId) {
            // [FIX 2026-08-06] 折叠聚合端点 (COLLAPSE_<id>) 不在 nodeColorMap 中,
            //   用 collapseColorMap (applyUpliftNodeColors 产出) fallback 取色, 避免折叠连线变黑.
            const sourceColor = nodeColorMap.get(sourceId) || collapseColorMap.get(sourceId)
            const targetColor = nodeColorMap.get(targetId) || collapseColorMap.get(targetId)

            // 判断源和目标是否在中心范围内
            const linkSourceCode = link.sourceCode || link.sourceName
            const linkTargetCode = link.targetCode || link.targetName
            // 只有 centerScopeHighlight 为 true 时，才使用 centerScopeBoCodes 判断
            // [FIX 2026-08-06] 折叠聚合端点 (COLLAPSE_<id>) 用 centerCollapseIds 判定中心范围,
            //   否则折叠连线被误判为双非中心 → 变黑。
            const isSourceCenter = centerScopeHighlight && (centerScopeBoCodes.includes(linkSourceCode) || centerCollapseIds.has(linkSourceCode))
            const isTargetCenter = centerScopeHighlight && (centerScopeBoCodes.includes(linkTargetCode) || centerCollapseIds.has(linkTargetCode))

            // [FIX 2026-08-02 v6] 连线颜色规则:
            //   1. 双中心 (区分中心范围) -> centerScopeColor 灰 (与中心节点灰色一致)
            //   2. 一中心一非中心 -> 非中心节点的颜色
            //   3. 双非中心 或 不区分中心范围 (centerScopeHighlight=false) -> 黑色
            let linkColor
            if (isSourceCenter && isTargetCenter) {
              linkColor = centerScopeColor
            } else if (isSourceCenter) {
              linkColor = targetColor || sourceColor || '#333333'
            } else if (isTargetCenter) {
              linkColor = sourceColor || targetColor || '#333333'
            } else {
              linkColor = '#000000'
            }

            // 关键修复 v26: mermaid 11 对 link label "|" 内空字符串或带特殊字符 ("\\n, |) 报 "Syntax error in text"
            // 1) 替换 | → /
            // 2) 替换换行 → 空格
            // [v39 关系线标题修复] 3) 优先用 code (关系实例编码 e.g. "ORDER-USER-01"),
            //    fallback 到 relationCode (关系类型编码 e.g. "DEPENDS_ON"),
            //    再 fallback 到 relationDesc (描述)
            // 4) 如果全都空或纯空白, 输出无 label 的 link
            const rawCode = (link.code && String(link.code).trim())
              ? link.code
              : (link.relationCode && String(link.relationCode).trim())
                ? link.relationCode
                : (link.relationDesc && String(link.relationDesc).trim())
                  ? link.relationDesc
                  : ''
            let safeCode = ''
            if (rawCode) {
              safeCode = String(rawCode)
                .replace(/\|/g, '/')
                .replace(/[\r\n]+/g, ' ')
                .replace(/"/g, "'")
                .trim()
            }
            const labelPart = safeCode ? `|"${safeCode}"|` : ''
            mermaidCode += getArrowSyntax(sourceId, targetId, safeCode, link)

            mermaidCode += `  linkStyle ${index} ${getLinkStyle(linkColor)}\n`

            linkColorMappings.push({
              index: index,
              sourceId: sourceId,
              targetId: targetId,
              color: linkColor
            })

            if (relationDescriptions) {
              // [v33 关键修复] 从 sourceId/targetId 反查节点名, 确保 tooltip 显示正确
              // 之前直接用 link.sourceName/targetName, 业务数据可能只有 sourceCode/targetCode
              // 没有 sourceName/targetName, 导致 tooltip 显示空
              const resolvedSourceName = nodeIdToNameMap.get(sourceId) || link.sourceName || ''
              const resolvedTargetName = nodeIdToNameMap.get(targetId) || link.targetName || ''
              // [v39 关系线标题修复] relationCode 优先用 link.code (实例编码), fallback 到 link.relationCode
              // 这样 tooltip 的第一行也显示"关系编码"而不是"关系类型编码"
              const resolvedRelationCode = link.code || link.relationCode || ''
              relationDescriptions.push({
                sourceName: resolvedSourceName,
                targetName: resolvedTargetName,
                source: sourceId,
                target: targetId,
                relationCode: resolvedRelationCode,
                label: resolvedRelationCode,
                relationDesc: link.relationDesc || '',
                // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code)
                relationType: link.relationType || '',
                // [v34 双向支持] 关系方向 (推/拉/双向)
                relationDirection: link.relationDirection || '',
                // [FIX 2026-06-30] 透传统数数组, 供 tooltip 按类别过滤
                annotationContent: link.annotationContent || '',
                annotationCategory: link.annotationCategory || 'info',
                annotationContents: link.annotationContents || [],
                annotationCategories: link.annotationCategories || [],
                sourceCode: link.sourceCode,
                targetCode: link.targetCode,
                // [OPT 2026-08-06] 透传端点显示层级 (0=domain/1=subDomain/2=serviceModule/3=BO), 供 tooltip 隐藏"高层级说明行"
                sourceLevel: link.sourceLevel ?? 3,
                targetLevel: link.targetLevel ?? 3,
                // [AGG 2026-08-09] 透传 childRelations: 融合后的底层关系数组 (由 fuseLinks 从
                //   members>1 的组生成). 供 tooltip 统计聚合连线 (领域/子领域/服务模块级别)
                //   的关系数量/方向/类型分布. 缺失时 tooltip 回退到"共 1 条".
                childRelations: link.childRelations || []
              })
            }
          }
        })

        // [ELK-FLAT 2026-08-14] 无边框打平 ELK 分组 → 布局辅助虚拟边 (透明不可见).
        //   背景: ELK 对 subgraph 内互不连通的节点一字排开 (INV 58 节点单行 11737px),
        //   打平分组 (inner/boundary visible=false) 已把节点渲染到父级, 此处追加虚拟链式边
        //   引导 ELK 把节点排成多列网格 (见 groupedLayout.buildLayoutHelperEdges).
        //   透明样式避免视觉污染; linkStyle 索引从真实边数量起算 (真实边 index 0..N-1),
        //   不参与 linkColorMappings/relationDescriptions (tooltip/取色等逻辑不受影响).
        const helperEdges = (layoutCode && layoutCode.layoutHelperEdges) || []
        if (helperEdges.length > 0) {
          const helperBaseIndex = businessObjectLinks.length
          helperEdges.forEach((e) => {
            mermaidCode += `  ${e.source} --> ${e.target}\n`
          })
          helperEdges.forEach((e, idx) => {
            mermaidCode += `  linkStyle ${helperBaseIndex + idx} stroke-width:0,opacity:0\n`
          })
        }

        mermaidCode += generateClassDefs()

        return {
          mermaidCode,
          nodeColorMappings,
          linkColorMappings,
          // [FOLD-COLOR 2026-08-08] 中性灰折叠节点集合透出: 供上层(MermaidComponent)在渲染后
          //   弹出 ElMessage 提示"该折叠节点含多分组, 已显示为中性灰".
          neutralCollapseIds: upliftStyleResult.neutralCollapseIds
        }
      }
    }

    let subgraphId = 1
    
    // subgraph 内部方向跟随整体方向：LR=水平排列，TB=垂直排列
    const subgraphDirection = actualDirection
    
    const reversedGroups = Array.from(optimizedGroups.entries()).reverse()
    let groupIndex = 0
    reversedGroups.forEach(([groupName, group]) => {
      const subId = `SG${groupIndex + 1}`
      groupIndex++

      const allNodesCenter = group.nodes.every(n => n.isCenter)
      const centerMark = allNodesCenter ? '◆' : ''
      let subgraphTitle
      if (group.info.type === 'submodule') {
        subgraphTitle = `${centerMark}${groupName}\\n(${group.info.grandparent}/${group.info.parent})`
      } else if (group.info.type === 'module') {
        subgraphTitle = `${centerMark}${groupName}\\n(${group.info.parent})`
      } else {
        subgraphTitle = centerMark + groupName
      }

      const groupColor = colorMap.get(groupName) || BLOCK_DIAGRAM_STYLES.container.fill

      // [FOLD 2026-08-05] FR-005: SG 兜底路径也要过滤"被隐藏的 BO 叶" (折叠分组 + 禁用 BO 叶).
      //   "仅服务模块"模板下服务模块分组内所有 BO 均被禁用 → visibleNodes 可能为空.
      //   此时仍渲染 subgraph 标题 (空盒子), 保留服务模块层级 (FR-005 语义: 服务模块启用).
      const visibleNodes = group.nodes.filter(n => !hiddenBoIds.has(n.id))

      mermaidCode += `  subgraph ${subId}["${subgraphTitle}"]\n`
      mermaidCode += `    direction ${subgraphDirection}\n`

      visibleNodes.forEach(node => {
        const centerMark = node.isCenter ? '◆' : ''
        // [TEMPLATE 2026-08-11] BO 标签统一走模板 (名称\n编码 两行)，中心标记经 opts 传入
        const displayText = businessObjectLabel(node, { centerMark })
        mermaidCode += `    ${node.id}["${displayText}"]:::node\n`
      })

      mermaidCode += `  end\n`

      mermaidCode += `  style ${subId} ${getContainerStyle(groupColor)}\n`
    })

    const nodeColorMappings = []
    // [FIX 2026-07-31 v3] 颜色分组 + classDef + class 修复 (覆盖无 layoutControlConfig 路径)
    //   之前只用 style 命令, Mermaid 11 base theme 下 CSS specificity 不够, 切换 colorGroupBy 后变灰。
    //   现在改用 mermaid 11 推荐的 classDef + class 形式 + style 兜底。
    const textColorB = data.nodeTextColor || '#000000'
    const classColorMapB = new Map()
    let classIdxB = 0
    businessObjectNodes.forEach(node => {
      // 优先使用 code 查找 id，避免同名不同编码的对象冲突
      const nodeCode = node.code
      const id = nodeCode ? nodeCodeToIdMap.get(nodeCode) : nodeNameToIdMap.get(node.originalName || node.name)
      // [FOLD 2026-08-05] FR-005: 跳过被隐藏的 BO 叶 (折叠分组 + 禁用 BO 叶)
      if (hiddenBoIds.has(id)) return
      const nodeColor = nodeColorMap.get(id) || '#FF9AA2'
      // [FIX 2026-08-02 v5] 回到原方案: 中心节点 fill = centerScopeColor (指定颜色), 默认边框
      const isCenter = centerNodeIds.has(id)
      const finalColor = isCenter ? centerScopeColor : nodeColor
      if (!classColorMapB.has(finalColor)) {
        const className = `boColor${classIdxB++}`
        classColorMapB.set(finalColor, className)
        mermaidCode += `  classDef ${className} ${getNodeStyle(finalColor, textColorB)}\n`
      }
      const className = classColorMapB.get(finalColor)
      mermaidCode += `  class ${id} ${className}\n`
      mermaidCode += `  style ${id} ${getNodeStyle(finalColor, textColorB)}\n`
      nodeColorMappings.push({ nodeId: id, color: nodeColor, nodeCode: node.code, nodeName: node.originalName || node.name, isCenter })
    })

    const businessObjectLinks = fuseLinks(data.links).filter(link => {
      let found = false
      if (link.sourceCode && link.targetCode) {
        found = nodeCodeToIdMap.has(link.sourceCode) && nodeCodeToIdMap.has(link.targetCode)
      }
      if (!found) {
        found = nodeNameToIdMap.has(link.sourceName) && nodeNameToIdMap.has(link.targetName)
      }
      if (!found) return false
      // [FOLD 2026-08-05] FR-005: 过滤连到"被隐藏 BO 叶"的连线 (折叠分组 + 禁用 BO 叶)
      const srcId = (link.sourceCode && nodeCodeToIdMap.get(link.sourceCode)) ||
                    (link.sourceName && nodeNameToIdMap.get(link.sourceName))
      const tgtId = (link.targetCode && nodeCodeToIdMap.get(link.targetCode)) ||
                    (link.targetName && nodeNameToIdMap.get(link.targetName))
      if (hiddenBoIds.has(srcId) || hiddenBoIds.has(tgtId)) return false
      return true
    })

    const linkColorMappings = []
    businessObjectLinks.forEach((link, index) => {
      let sourceId = null
      let targetId = null

      if (link.sourceCode) {
        sourceId = nodeCodeToIdMap.get(link.sourceCode)
      }
      if (link.targetCode) {
        targetId = nodeCodeToIdMap.get(link.targetCode)
      }

      if (!sourceId) {
        sourceId = nodeNameToIdMap.get(link.sourceName)
      }
      if (!targetId) {
        targetId = nodeNameToIdMap.get(link.targetName)
      }

      if (sourceId && targetId) {
        const sourceColor = nodeColorMap.get(sourceId)
        const targetColor = nodeColorMap.get(targetId)

        let sourceGroupKey = '', targetGroupKey = ''
        sortedGroups.forEach((group) => {
          if (group.nodes.some(n => n.id === sourceId)) {
            if (colorGroupBy === 'serviceModule') {
              sourceGroupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
            } else if (colorGroupBy === 'subDomain') {
              sourceGroupKey = group.info.subDomain
            } else {
              sourceGroupKey = group.info.domain
            }
          }
          if (group.nodes.some(n => n.id === targetId)) {
            if (colorGroupBy === 'serviceModule') {
              targetGroupKey = group.info.serviceModuleName || group.info.serviceModule || group.info.name
            } else if (colorGroupBy === 'subDomain') {
              targetGroupKey = group.info.subDomain
            } else {
              targetGroupKey = group.info.domain
            }
          }
        })

        // [FIX 2026-08-02 v6] 与 layout 路径一致的连线颜色规则 (含中心范围判定)
        const linkSourceCodeB = link.sourceCode || link.sourceName
        const linkTargetCodeB = link.targetCode || link.targetName
        const isSourceCenterB = centerScopeHighlight && (centerScopeBoCodes.includes(linkSourceCodeB) || centerCollapseIds.has(linkSourceCodeB))
        const isTargetCenterB = centerScopeHighlight && (centerScopeBoCodes.includes(linkTargetCodeB) || centerCollapseIds.has(linkTargetCodeB))
        const linkColor = getLinkColor(sourceGroupKey, targetGroupKey, sourceColor, targetColor, {
          isSourceCenter: isSourceCenterB,
          isTargetCenter: isTargetCenterB,
          centerScopeColor
        })

        // 关键修复 v26: 见上 (line 886) 的 mermaid label 特殊字符处理
        // [v39 关系线标题修复] 优先 code → relationCode → relationDesc (与上面 line 895 保持一致)
        const rawCode2 = (link.code && String(link.code).trim())
          ? link.code
          : (link.relationCode && String(link.relationCode).trim())
            ? link.relationCode
            : (link.relationDesc && String(link.relationDesc).trim())
              ? link.relationDesc
              : ''
        let safeCode2 = ''
        if (rawCode2) {
          safeCode2 = String(rawCode2)
            .replace(/\|/g, '/')
            .replace(/[\r\n]+/g, ' ')
            .replace(/"/g, "'")
            .trim()
        }
        const labelPart2 = safeCode2 ? `|"${safeCode2}"|` : ''
        mermaidCode += getArrowSyntax(sourceId, targetId, safeCode2, link)

        mermaidCode += `  linkStyle ${index} ${getLinkStyle(linkColor)}\n`

        linkColorMappings.push({
          index: index,
          sourceId: sourceId,
          targetId: targetId,
          color: linkColor
        })

        if (relationDescriptions) {
          // [v33 关键修复] 从 sourceId/targetId 反查节点名, 确保 tooltip 显示正确
          const resolvedSourceName = nodeIdToNameMap.get(sourceId) || link.sourceName || ''
          const resolvedTargetName = nodeIdToNameMap.get(targetId) || link.targetName || ''
          // [v39 关系线标题修复] relationCode 优先用 link.code (实例编码), fallback 到 link.relationCode
          const resolvedRelationCode = link.code || link.relationCode || ''
          relationDescriptions.push({
            sourceName: resolvedSourceName,
            targetName: resolvedTargetName,
            source: sourceId,
            target: targetId,
            relationCode: resolvedRelationCode,
            label: resolvedRelationCode,
            relationDesc: link.relationDesc || '',
            // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code)
            relationType: link.relationType || '',
            // [v34 双向支持] 关系方向 (推/拉/双向)
            relationDirection: link.relationDirection || '',
            // [FIX 2026-06-30] 透传统数数组, 供 tooltip 按类别过滤
            annotationContent: link.annotationContent || '',
            annotationCategory: link.annotationCategory || 'info',
            annotationContents: link.annotationContents || [],
            annotationCategories: link.annotationCategories || [],
            sourceCode: link.sourceCode,
            targetCode: link.targetCode,
            // [OPT 2026-08-06] 透传端点显示层级 (0=domain/1=subDomain/2=serviceModule/3=BO), 供 tooltip 隐藏"高层级说明行"
            sourceLevel: link.sourceLevel ?? 3,
            targetLevel: link.targetLevel ?? 3
          })
        }
      }
    })

    mermaidCode += generateClassDefs()

    return {
      mermaidCode,
      nodeColorMappings,
      linkColorMappings,
      // [FOLD-COLOR 2026-08-08] 非分组路径无折叠聚合节点, 中性灰集合为空
      neutralCollapseIds: new Set()
    }
  }

  return {
    generateMermaidCode
  }
}

function generateGroupMermaid(group, nodeMap, definedNodes, actualDirection) {
  let code = ''
  const groupId = `G_${group.id.replace(/[^a-zA-Z0-9]/g, '_')}`
  const groupTitle = group.title || 'Group'
  const groupEnabled = group.enabled !== false

  if (!groupEnabled) {
    // 对于禁用的分组，只处理子元素（已提升），不处理自身的 containers
    if (group.children && group.children.length > 0) {
      group.children.forEach(child => {
        code += generateGroupMermaid(child, nodeMap, definedNodes, actualDirection)
      })
    }
    // 注意：禁用的分组不应该有 containers（已经buildVirtualContainers 中清除）
    if (group.containers && group.containers.length > 0) {
      group.containers.forEach((container, idx) => {
        if (container.nodes && container.nodes.length > 0) {
          // [PROVIDER 2026-08-04] 容器级可见/禁用：enabled=false 或 visible=false 时打平
          const containerEnabled = container.enabled !== false
          const containerVisible = container.visible !== false
          if (containerEnabled && containerVisible) {
            const containerId = `${groupId}_C${idx + 1}`
            const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')
            code += `  subgraph ${containerId}["${containerTitle}"]\n`
            code += `    direction ${actualDirection}\n`
            
            container.nodes.forEach(nodeId => {
              const node = nodeMap.get(nodeId)
              if (node && !definedNodes.has(nodeId)) {
                const displayText = businessObjectLabel(node)
                code += `    ${nodeId}["${displayText}"]:::node\n`
                definedNodes.add(nodeId)
              }
            })
            
            code += `  end\n`
          } else {
            container.nodes.forEach(nodeId => {
              const node = nodeMap.get(nodeId)
              if (node && !definedNodes.has(nodeId)) {
                const displayText = businessObjectLabel(node)
                code += `  ${nodeId}["${displayText}"]:::node\n`
                definedNodes.add(nodeId)
              }
            })
          }
        }
      })
    }
    return code
  }

  code += `  subgraph ${groupId}["${groupTitle}"]\n`
  code += `    direction ${actualDirection}\n`

  if (group.children && group.children.length > 0) {
    group.children.forEach(child => {
      code += generateGroupMermaid(child, nodeMap, definedNodes, actualDirection)
    })
  }

  if (group.containers && group.containers.length > 0) {
    group.containers.forEach((container, idx) => {
      if (container._isDirectNodesContainer) {
        if (container.nodes && container.nodes.length > 0) {
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = businessObjectLabel(node)
              code += `    ${nodeId}["${displayText}"]:::node\n`
              definedNodes.add(nodeId)
            }
          })
        }
        return
      }
      
      if (container.nodes && container.nodes.length > 0) {
        // [PROVIDER 2026-08-04] 容器级可见/禁用：enabled=false 或 visible=false 时
        //   容器边框不显示，节点打平渲染（外提）。enabled 语义与既有行为一致。
        const containerEnabled = container.enabled !== false
        const containerVisible = container.visible !== false
        if (containerEnabled && containerVisible) {
          const containerId = `${groupId}_C${idx + 1}`
          const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')
          code += `    subgraph ${containerId}["${containerTitle}"]\n`
          code += `      direction ${actualDirection}\n`
          
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = businessObjectLabel(node)
              code += `      ${nodeId}["${displayText}"]:::node\n`
              definedNodes.add(nodeId)
            }
          })
          
          code += `    end\n`
        } else {
          container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node && !definedNodes.has(nodeId)) {
              const displayText = businessObjectLabel(node)
              code += `    ${nodeId}["${displayText}"]:::node\n`
              definedNodes.add(nodeId)
            }
          })
        }
      }
    })
  }

  code += `  end\n`

  return code
}
