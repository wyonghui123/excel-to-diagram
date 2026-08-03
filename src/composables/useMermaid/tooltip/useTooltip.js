let tooltipInstance = null

// [v39 枚举解析修复] 同步从 EnumService._cache 读出 enum options 转为 {code -> {code, label}} map
// 之前只读 window.__relationTypeEnumMap, 该变量在生产中无人设置 → 中文名永远不显示
// 关键: EnumService.loadOptions 会写入 _cache, RelationFilterSection 加载 relation_type
//       任何调用 loadOptions('direction') 的组件也会写入 direction 缓存
// [v40 修复] 改用静态 import EnumService, 不再走 dynamic import
// 原因: dynamic import 是 async, getEnumService() 返回 Promise
//       getEnumMap 是同步调用, 在 Promise resolve 前 _enumServiceRef.current 一直是 null
//       → tooltip 第一次 hover 时 EnumService 还没加载, L2 永远 miss
// 静态 import 同步解析, 模块加载完成 _enumServiceRef.current 立即可用
// [v40.3 修复] 之前的 `import EnumServiceModule from '@/services/enumService.js'` 在 Vite 下被当作 CJS
//   interop 处理, EnumServiceModule 直接是 EnumService 对象本身 (没有 default/named 包装)
//   修复: 改用 namespace import, 然后用 mod.default || mod (Vite 会把 default export 作为 'default' key)
import * as EnumServiceNS from '@/services/enumService.js'
import { useDiagnostics } from '../core/useDiagnostics.js'
const _enumServiceRef = {
  current: EnumServiceNS?.default || (EnumServiceNS?._cache ? EnumServiceNS : null)
}

// [v40.2 修复] _enumMapCache 缺失声明 → 第一次 hover 触发 ReferenceError
//   症状: 浏览器 console 报 "_enumMapCache is not defined"
//   原因: v40 重构时只改了 import 方式, 漏掉把 L1 缓存 Map 声明回来
const _enumMapCache = new Map()

async function getEnumService() {
  // [v40] 静态 import 后 EnumService 已同步可用, 此函数保留为 API 兼容
  return _enumServiceRef.current
}

function buildMapFromCache(cached) {
  if (!cached || !Array.isArray(cached.data)) return null
  const map = {}
  let hasAny = false
  for (const opt of cached.data) {
    const code = (opt && (opt.value || opt.code)) || ''
    if (!code) continue
    map[code] = {
      code,
      label: (opt && (opt.label || opt.name)) || ''
    }
    hasAny = true
  }
  return hasAny ? map : null
}

function getEnumMap(enumTypeId) {
  if (typeof enumTypeId !== 'string' || !enumTypeId) return null

  // L1: 内部缓存 (避免每次 hover 都遍历 cache)
  // 修复 v39: 只缓存从 EnumService._cache (生产) 读到的结果, 不缓存 window 兜底结果
  //   → 避免单测中 window.__relationTypeEnumMap 切换时, 旧 map 被错误复用
  if (_enumMapCache.has(enumTypeId)) {
    return _enumMapCache.get(enumTypeId)
  }

  let map = null
  let fromService = false

  // L2: 从 EnumService._cache 取 (RelationFilterSection 等组件已写入)
  // 注: EnumService 在 SPA 启动时已 import, _cache 是同步可读
  try {
    const svc = _enumServiceRef.current
    if (svc && svc._cache && svc._cache.has(enumTypeId)) {
      map = buildMapFromCache(svc._cache.get(enumTypeId))
      fromService = true
    }
  } catch (e) {
    // 静默 fallback
  }

  // L3: 兜底 - window.__relationTypeEnumMap / __relationDirectionEnumMap (向后兼容单测)
  if (!map && typeof window !== 'undefined') {
    const winMap = enumTypeId === 'relation_type'
      ? window.__relationTypeEnumMap
      : enumTypeId === 'direction'
        ? window.__relationDirectionEnumMap
        : null
    if (winMap && typeof winMap === 'object') {
      map = winMap
    }
  }

  // 修复 v39: 只缓存 EnumService 读到的结果, window 兜底结果不缓存
  //   - 生产: EnumService 加载完后, L2 命中并缓存, 后续 hover 直接命中 L1
  //   - 测试: window.__relationTypeEnumMap 切换时, L3 不缓存 → 每次重读最新 window 值
  if (fromService && map) {
    _enumMapCache.set(enumTypeId, map)
  }
  return map
}

// [v39 方向 enum 预加载] 异步预加载 direction / relation_type 枚举
// 在 addMouseOverTooltips 第一次调用时触发, fire-and-forget
// 第二次 hover 时缓存已就绪
// [v40 强化] 改为导出 preloadEnums() 给 MermaidComponent 主动调用
//   - 原因: 之前 fire-and-forget 时, 用户在第一次 hover 前 EnumService 还没加载完 → tooltip 仍显示 code
//   - 修复: MermaidComponent 在 diagramData 加载完后 await preloadEnums(), 后续 hover 一定命中缓存
let _enumPreloadTriggered = false
export async function preloadEnums() {
  if (typeof window === 'undefined') return
  _enumPreloadTriggered = true
  console.log('[v40.3 诊断] preloadEnums STARTED')

  try {
    const EnumService = await getEnumService()
    console.log('[v40.3 诊断] preloadEnums EnumService =', EnumService ? 'OK' : 'NULL', '_cache=', !!EnumService?._cache)
    if (!EnumService || !EnumService._cache) return
    if (!EnumService._cache.has('direction')) {
      console.log('[v40.3 诊断] preloadEnums loading direction...')
      const dirResult = await EnumService.loadOptions('direction', { cache: true, throwError: false })
      console.log('[v40.3 诊断] preloadEnums direction loaded:', dirResult?.length, 'options')
      _enumMapCache.delete('direction')
    }
    if (!EnumService._cache.has('relation_type')) {
      console.log('[v40.3 诊断] preloadEnums loading relation_type...')
      const typeResult = await EnumService.loadOptions('relation_type', { cache: true, throwError: false })
      console.log('[v40.3 诊断] preloadEnums relation_type loaded:', typeResult?.length, 'options')
      _enumMapCache.delete('relation_type')
    }
    console.log('[v40.3 诊断] preloadEnums DONE cacheSize=', EnumService._cache.size)
  } catch (e) {
    _enumPreloadTriggered = false  // 允许下次重试
    console.warn('[useTooltip.preloadEnums] failed:', e?.message || e)
  }
}

function triggerEnumPreload() {
  if (_enumPreloadTriggered) return
  if (typeof window === 'undefined') return
  // [v40 优化] 改为走 preloadEnums (Promise), 避免 fire-and-forget 早期 hover 失效
  preloadEnums()
}

export function useTooltip() {

  // [P0-A 2026-08-03] 接入 diag 埋点 — highlight/clear/match 失败时 recordStepMeta,
  //   之前 useTooltip 高亮完全无可观测信号, 与 annotationOverlay 的 .annotation-highlighted
  //   DOM 查询不对齐, "点了没反应" 类问题排查困难.
  // [P0-B 2026-08-03] 通过 diag.setHighlightState 暴露闭包内的 selectedElements 快照,
  //   window.__archPage.mermaid.highlight 一键读取.
  const diag = useDiagnostics()

  // [P1-B 2026-08-03] 拖动守卫: 跨 click 事件保留 mousedown 起点.
  //   用户拖动图表 (panning) 后浏览器仍 fire click 事件, 会误触发 clearHighlight 清掉高亮.
  //   与 annotationOverlay.onSvgClick 的 isDraggingState 守卫对齐 (那里用 mousedown/mousemove/mouseup).
  //   这里用更简单的位移判定: mousedown 记录起点, click 时位移 > 5px 视为拖动, 跳过 clear.
  let _mouseDownPos = null

  /**
   * [P0-B] 把 selectedElements (含 DOM 引用) 序列化为可观测快照, 同步到 diag.
   *   DOM 引用不暴露到 window (会泄漏 / 影响测试稳定性), 只暴露 code/id/text 等纯数据.
   */
  const _snapshotHighlight = (selectedElements) => {
    const snapNode = (el) => {
      if (!el) return null
      return {
        code: el.getAttribute ? (el.getAttribute('data-code') || null) : null,
        id: el.id || null,
        tag: el.tagName || null
      }
    }
    const snapPath = (p) => {
      if (!p) return null
      const d = (p.getAttribute && p.getAttribute('d')) || ''
      return {
        relationCode: (p.getAttribute && p.getAttribute('data-relation-code')) || null,
        dSnippet: d.substring(0, 50)
      }
    }
    const snapLabel = (l) => {
      if (!l) return null
      return { text: ((l.textContent || '')).trim().substring(0, 50) }
    }
    const snapshot = {
      hasHighlight: !!(selectedElements.path || selectedElements.label || selectedElements.sourceNode || selectedElements.targetNode),
      path: snapPath(selectedElements.path),
      label: snapLabel(selectedElements.label),
      sourceNode: snapNode(selectedElements.sourceNode),
      targetNode: snapNode(selectedElements.targetNode)
    }
    diag.setHighlightState(snapshot)
    return snapshot
  }

  const createTooltipElement = () => {
    let tooltip = document.getElementById('mermaid-tooltip')
    if (!tooltip) {
      tooltip = document.createElement('div')
      tooltip.id = 'mermaid-tooltip'
      tooltip.style.position = 'fixed'
      tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.85)'
      tooltip.style.color = 'white'
      tooltip.style.padding = '10px 14px'
      tooltip.style.borderRadius = '6px'
      tooltip.style.fontSize = '13px'
      tooltip.style.zIndex = '100000'
      tooltip.style.pointerEvents = 'none'
      tooltip.style.visibility = 'hidden'
      tooltip.style.whiteSpace = 'pre-line'
      tooltip.style.lineHeight = '1.5'
      tooltip.style.maxWidth = '300px'
      tooltip.style.wordWrap = 'break-word'
      tooltip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)'
      document.body.appendChild(tooltip)
    }
    tooltipInstance = tooltip
    return tooltip
  }

  const showTooltip = (tooltip, text, x, y) => {
    tooltip.textContent = text
    tooltip.style.visibility = 'visible'
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  const hideTooltip = (tooltip) => {
    tooltip.style.visibility = 'hidden'
  }

  const moveTooltip = (tooltip, x, y) => {
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  // [v34 双向支持] 关系类型 (BusinessRelationType 枚举 code → 中文名)
  // [v39 双向支持增强] 关系方向 (direction 枚举) 也走相同解析逻辑
  // 导出供单测覆盖 (useTooltip.spec.js)
  // [FIX 2026-06-30] 新增 annotationFilter 参数:
  //   - undefined (未传): 走老逻辑, 用 relation.annotationContent (向后兼容单测)
  //   - [] (空数组, 用户未选类别): 不展示备注行
  //   - 非空数组: 只展示 relation.annotationContents 中 category 在 filter 内的备注
  // [FIX 2026-08-03] 新增 childRelations 支持:
  //   - SM 图关系聚合多条 BO 级子关系, childRelations 携带每条子关系完整元数据
  //   - 有 childRelations 时展示父关系概览 + 子关系列表; 否则走单关系老逻辑 (BO 图/单测兼容)

  // 关系类型 code → "中文名 (CODE)" 标签 (无枚举时显示原始 code)
  const _resolveTypeLabel = (relationType) => {
    if (!relationType) return ''
    const typeMap = getEnumMap('relation_type')
    if (typeMap) {
      const enumOption = typeMap[relationType]
      if (enumOption && enumOption.label) {
        return `${enumOption.label} (${relationType})`
      }
    }
    return relationType
  }

  // 关系方向 code → "中文 (CODE)" 标签 (无枚举时显示原始 code)
  const _resolveDirectionLabel = (relationDirection) => {
    if (!relationDirection) return ''
    const dirMap = getEnumMap('direction')
    if (dirMap) {
      const enumOption = dirMap[relationDirection]
      if (enumOption && enumOption.label) {
        return `${enumOption.label} (${relationDirection})`
      }
    }
    return relationDirection
  }

  // 备注行: 按 annotationFilter 过滤, 返回拼接后的字符串 (空则不展示)
  const _resolveAnnotationLine = (relation, annotationFilter) => {
    if (annotationFilter === undefined) {
      // 老逻辑: 单测路径, relation.annotationContent 是单字符串
      return relation.annotationContent || ''
    }
    if (Array.isArray(annotationFilter) && annotationFilter.length > 0) {
      // 过滤模式: 优先用复数数组, fallback 到单数字段
      const contents = relation.annotationContents
      const categories = relation.annotationCategories
      if (Array.isArray(contents) && contents.length > 0 && Array.isArray(categories)) {
        const matched = contents
          .map((c, idx) => ({ content: c, category: categories[idx] || 'info' }))
          .filter(item => item.content && item.category && annotationFilter.includes(item.category))
          .map(item => item.content)
        return matched.join('; ')
      }
      if (relation.annotationContent && relation.annotationCategory && annotationFilter.includes(relation.annotationCategory)) {
        return relation.annotationContent
      }
    }
    // annotationFilter === [] 或其它: 不展示
    return ''
  }

  // 格式化单个关系的完整文本块 (header + body), 可选缩进 (用于子关系列表)
  const _formatRelationBlock = (relation, annotationFilter, indent = '') => {
    const relationCode = relation.relationCode || ''
    const relationDesc = relation.relationDesc || '无关系说明'
    const sourceName = relation.sourceName || ''
    const targetName = relation.targetName || ''
    const relationType = relation.relationType || ''
    const relationDirection = relation.relationDirection || ''

    // 多行 desc 缩进: 把 desc 内部的换行也加上缩进, 保持子关系块对齐
    const indentedDesc = indent ? String(relationDesc).replace(/\n/g, `\n${indent}`) : relationDesc

    let text = `${indent}${relationCode}\n${indent}${sourceName} → ${targetName}`

    const typeLabel = _resolveTypeLabel(relationType)
    if (typeLabel) text += `\n${indent}类型: ${typeLabel}`

    const dirLabel = _resolveDirectionLabel(relationDirection)
    if (dirLabel) text += `\n${indent}方向: ${dirLabel}`

    text += `\n${indent}${indentedDesc}`

    const annotationLine = _resolveAnnotationLine(relation, annotationFilter)
    if (annotationLine) text += `\n${indent}备注: ${annotationLine}`

    return text
  }

  const formatTooltipText = (relation, annotationFilter) => {
    if (!relation) return '无关系说明'

    // [FIX 2026-08-03] SM 图: childRelations 非空时展示父关系概览 + 所有子关系列表
    //   (SM 下源和目标 BO 对的列表, 每条含 source/target/type/direction/desc/annotation)
    //   BO 图/单测: childRelations 缺失或空 → 走单关系老逻辑 (向后兼容)
    const childRelations = Array.isArray(relation.childRelations) ? relation.childRelations : []
    if (childRelations.length > 0) {
      const parentCode = relation.relationCode || ''
      const parentSource = relation.sourceName || ''
      const parentTarget = relation.targetName || ''
      let text = `${parentCode}\n${parentSource} → ${parentTarget}`
      text += `\n共 ${childRelations.length} 条子关系:`
      childRelations.forEach((child, idx) => {
        const block = _formatRelationBlock(child, annotationFilter, '    ')
        text += `\n\n[${idx + 1}] ${block}`
      })
      return text
    }

    return _formatRelationBlock(relation, annotationFilter)
  }

  const createSelectionState = () => {
    return {
      path: null,
      label: null,
      sourceNode: null,
      targetNode: null
    }
  }

  const clearHighlight = (selectedElements) => {
    // [P0-A] 记录清高亮前的状态 — 排查"高亮莫名消失"类问题
    const hadHighlight = !!(selectedElements.path || selectedElements.sourceNode || selectedElements.targetNode || selectedElements.label)
    if (hadHighlight) {
      diag.recordStepMeta('useTooltipClearHighlight', {
        hadPath: !!selectedElements.path,
        hadLabel: !!selectedElements.label,
        hadSource: !!selectedElements.sourceNode,
        hadTarget: !!selectedElements.targetNode
      })
    }

    if (selectedElements.path) {
      selectedElements.path.style.strokeWidth = '2px'
      selectedElements.path.style.removeProperty('filter')
      selectedElements.path = null
    }

    if (selectedElements.sourceNode) {
      const rect = selectedElements.sourceNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.sourceNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.sourceNode = null
    }

    if (selectedElements.targetNode) {
      const rect = selectedElements.targetNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.targetNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.targetNode = null
    }

    if (selectedElements.label) {
      selectedElements.label = null
    }

    // [P0-B] 同步空快照到 diag (window.__archPage.mermaid.highlight 反映 cleared 状态)
    if (hadHighlight) {
      _snapshotHighlight(selectedElements)
    }
  }

  const highlightNode = (svg, nodeId, type, selectedElements) => {
    let nodeElement = svg.querySelector(`#${nodeId}`)
    let matchStrategy = 'id-selector'

    if (!nodeElement) {
      const allNodes = svg.querySelectorAll('.node')
      // [P1-A 2026-08-03] 边界检查: 之前 node.id.includes(nodeId) 会让 PUM01 误匹配 PUM010
      //   (因为 "PUM010".includes("PUM01") === true). 改为:
      //   1) 精确 === 优先
      //   2) fallback 到边界正则 (^|[^a-zA-Z0-9])nodeId([^a-zA-Z0-9]|$),
      //      要求 nodeId 前后是非字母数字 (含 - _ 边界) 或字符串首尾.
      //      PUM010 的 "0" 是数字 → 不匹配, 正确排除.
      //   边界正则同时兼容 mermaid 11 自动加前缀 (flowchart-PUM01-1) 的 case.
      const escapedId = nodeId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const boundaryRe = new RegExp(`(^|[^a-zA-Z0-9])${escapedId}([^a-zA-Z0-9]|$)`)
      for (const node of allNodes) {
        if (node.id === nodeId) {
          nodeElement = node
          matchStrategy = 'id-exact'
          break
        }
        if (node.id && boundaryRe.test(node.id)) {
          nodeElement = node
          matchStrategy = 'id-boundary'
          break
        }
      }
    }

    if (!nodeElement) {
      nodeElement = svg.querySelector(`[data-id="${nodeId}"]`)
      if (nodeElement) matchStrategy = 'data-id'
    }

    if (nodeElement) {
      const nodeContainer = nodeElement.closest('.node') || nodeElement

      const rect = nodeContainer.querySelector('rect, polygon')
      if (rect) {
        rect.style.stroke = '#FF6B6B'
        rect.style.strokeWidth = '4px'
        rect.style.filter = 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
      }

      const label = nodeContainer.querySelector('.nodeLabel, text')
      if (label) {
        label.style.fontWeight = 'bold'
        label.style.fontSize = '16px'
      }

      if (type === 'source') {
        selectedElements.sourceNode = nodeContainer
      } else {
        selectedElements.targetNode = nodeContainer
      }
      // [P0-A] 命中埋点: 记录 nodeId + 匹配策略, 排查"高亮错节点"类问题
      diag.recordStepMeta('useTooltipHighlightNode', {
        nodeId, type, matchStrategy, found: true
      })
    } else {
      // [P0-A] 匹配失败埋点 — 排查"点 edge 但 source/target 没高亮"类问题
      diag.recordStepMeta('useTooltipHighlightNode', {
        nodeId, type, matchStrategy: 'none', found: false
      })
    }
  }

  /**
   * [X] 已移除：不再需要 JavaScript 设置背景
   * 所有 edgeLabel 背景样式由 CSS .edge-label-clean 类统一管理
   */
  // const setLabelBackground = (edgeLabels) => { ... }

  // 实例级状态：每个 useTooltip() 调用都有自己的清理列表
  let _cleanupFns = []
  let _currentSvg = null

  // 注册可清理的事件监听器
  const addListener = (element, event, handler, options) => {
    element.addEventListener(event, handler, options)
    _cleanupFns.push(() => element.removeEventListener(event, handler, options))
  }

  const matchPathsToRelations = (svg, labels, relationDescriptions) => {
    const pathToRelationMap = new Map()
    const relationCodeMap = new Map()

    relationDescriptions.forEach(relation => {
      if (relation.relationCode) {
        relationCodeMap.set(relation.relationCode, relation)
      }
    })

    labels.forEach((label) => {
      const labelText = label.textContent || label.innerHTML
      const relation = relationCodeMap.get(labelText.trim())
      if (relation) {
        pathToRelationMap.set(label, relation)
      }
    })

    const edgeContainers = Array.from(svg.querySelectorAll('.edgePath'))
    const directEdgePaths = Array.from(svg.querySelectorAll('path.flowchart-link'))
    const realEdgePaths = []

    edgeContainers.forEach((edgeContainer, edgeIndex) => {
      const path = edgeContainer.querySelector('path')
      if (path) {
        realEdgePaths.push({ path, index: edgeIndex })
      }
    })

    directEdgePaths.forEach((path, edgeIndex) => {
      if (!realEdgePaths.some(item => item.path === path)) {
        realEdgePaths.push({ path, index: edgeIndex + edgeContainers.length })
      }
    })

    realEdgePaths.forEach((edgePathInfo, idx) => {
      if (idx < relationDescriptions.length) {
        const relation = relationDescriptions[idx]
        pathToRelationMap.set(edgePathInfo.path, relation)
      }
    })

    return { pathToRelationMap, realEdgePaths }
  }

  const getEdgeLabels = (svg) => {
    const allEdgeLabels = svg.querySelectorAll('.edgeLabel')
    return Array.from(allEdgeLabels).filter(el => el.getBBox)
  }

  const setupLabelEvents = (label, index, tooltip, relationDescriptions, pathToRelationMap, labels, selectedElements, svg, realEdgePaths, annotationFilter) => {
    const onEnter = (e) => {
      let tooltipText = '无关系说明'
      const labelText = label.textContent || label.innerHTML
      const relation = relationDescriptions.find(r => r.relationCode && r.relationCode.trim() === labelText.trim())
      if (relation) {
        tooltipText = formatTooltipText(relation, annotationFilter)
      }
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    }
    const onMove = (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    }
    const onLeave = () => {
      hideTooltip(tooltip)
    }
    const onClick = (e) => {
      e.stopPropagation()
      clearHighlight(selectedElements)
      selectedElements.label = label

      const relation = pathToRelationMap.get(label)

      if (relation) {
        const correspondingPath = realEdgePaths.find((item) => item.path && pathToRelationMap.get(item.path) === relation)?.path

        if (correspondingPath) {
          selectedElements.path = correspondingPath
          correspondingPath.style.strokeWidth = '4px'
          correspondingPath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
        }
      }
      // [P0-A] 埋点 + [P0-B] 状态快照同步到 diag
      diag.recordStepMeta('useTooltipLabelClick', {
        hasRelation: !!relation,
        relationCode: relation?.relationCode || null,
        hasPath: !!selectedElements.path
      })
      _snapshotHighlight(selectedElements)
    }

    addListener(label, 'mouseenter', onEnter)
    addListener(label, 'mousemove', onMove)
    addListener(label, 'mouseleave', onLeave)
    addListener(label, 'click', onClick)
  }

  const setupPathEvents = (path, tooltip, pathToRelationMap, labels, selectedElements, svg, annotationFilter) => {
    const onEnter = (e) => {
      const relation = pathToRelationMap.get(path)
      const tooltipText = relation ? formatTooltipText(relation, annotationFilter) : '无关系说明'
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    }
    const onMove = (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    }
    const onLeave = () => {
      hideTooltip(tooltip)
    }
    const onClick = (e) => {
      e.stopPropagation()

      selectedElements.path = null
      selectedElements.label = null
      selectedElements.sourceNode = null
      selectedElements.targetNode = null
      selectedElements.path = path

      const relation = pathToRelationMap.get(path)

      if (relation) {
        const relationCode = relation.relationCode
        const correspondingLabel = Array.from(labels).find((label) => {
          const labelText = label.textContent || label.innerHTML
          return labelText.trim() === relationCode
        })

        if (correspondingLabel) {
          selectedElements.label = correspondingLabel
        }

        highlightNode(svg, relation.source, 'source', selectedElements)
        highlightNode(svg, relation.target, 'target', selectedElements)
      }
      // [P0-A] 埋点 + [P0-B] 状态快照同步到 diag
      diag.recordStepMeta('useTooltipPathClick', {
        hasRelation: !!relation,
        relationCode: relation?.relationCode || null,
        source: relation?.source || null,
        target: relation?.target || null
      })
      _snapshotHighlight(selectedElements)
    }

    addListener(path, 'mouseenter', onEnter)
    addListener(path, 'mousemove', onMove)
    addListener(path, 'mouseleave', onLeave)
    addListener(path, 'click', onClick)
  }

  const addTrailingDottedLines = (svg, labels, diagramType, hideTails = false) => {
    if (diagramType !== 'businessObject' && diagramType !== 'serviceModule') return

    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    labels.forEach((label, index) => {
      if (!label.getBBox) {
        console.warn(`标签 ${index} 不是 SVG 元素，跳过`);
        return
      }

      const labelTransform = label.getAttribute('transform') || ''
      const translateMatch = labelTransform.match(/translate\(([^,]+),\s*([^)]+)\)/)

      if (!translateMatch) {
        console.warn(`标签 ${index} 没有 Transform`)
        return
      }

      const translateX = parseFloat(translateMatch[1])
      const translateY = parseFloat(translateMatch[2])

      // 获取标签内容元素（foreignObject 或文本）
      const foreignObject = label.querySelector('foreignObject')
      let contentWidth = 0
      let contentHeight = 0

      if (foreignObject) {
        // 如果有 foreignObject，使用其子元素的实际尺寸
        const foDiv = foreignObject.querySelector('div')
        if (foDiv) {
          const rect = foDiv.getBoundingClientRect()
          contentWidth = rect.width
          contentHeight = rect.height
        }
      }

      // 如果无法获取内容尺寸，使用 getBBox 作为备选
      const labelBBox = label.getBBox()
      const finalWidth = contentWidth > 0 ? contentWidth : labelBBox.width
      const finalHeight = contentHeight > 0 ? contentHeight : labelBBox.height

      // 计算标签中心位置（基于 transform）
      const labelCenterX = translateX
      const labelCenterY = translateY
      const labelLeft = labelCenterX - finalWidth / 2
      const labelTop = labelCenterY - finalHeight / 2

      const labelParent = label.parentElement

      // [OK] 纯 CSS 方案：添加 CSS 类，由 CSS 隐藏装饰元素
      label.classList.add('edge-label-clean')

      // [OK] 创建白色背景 rect
      // 使用 requestAnimationFrame 确保 Mermaid 渲染完成后再设置
      requestAnimationFrame(() => {
        // 获取 label 的位置和大小
        try {
          // [v40.4 修复] 之前用 label.getBBox() 拿到的是含 foreignObject overflow 的 bbox
          //   （如 185x24），比实际文字 (~70x11) 大 2.5x，导致白底过大
          //   修复: 用 foreignObject 的子 div 实际尺寸 + 4px 边距，刚好包住文字
          const fo = label.querySelector('foreignObject')
          if (!fo) return

          const innerLabelG = label.querySelector('g.label')
          // 实际内容尺寸: 优先取 fo 子 div 的 clientRect，否则用 fo 属性
          let contentW = 0
          let contentH = 0
          let scale = 1
          const foDiv = fo.querySelector('div')
          if (foDiv) {
            const rect = foDiv.getBoundingClientRect()
            // 转成 SVG 用户单位: 实际像素 / SVG 缩放比例
            const svgEl = label.closest('svg')
            if (svgEl) {
              const svgRect = svgEl.getBoundingClientRect()
              const viewBox = svgEl.viewBox?.baseVal
              if (viewBox && viewBox.width > 0) {
                scale = svgRect.width / viewBox.width
              }
            }
            contentW = rect.width / (scale || 1)
            contentH = rect.height / (scale || 1)
          }
          if (!contentW) contentW = parseFloat(fo.getAttribute('width')) || 100
          if (!contentH) contentH = parseFloat(fo.getAttribute('height')) || 24

          // 边距: 上下 1px, 左右 2px (CSS labelBkg padding 4px 8px 已由 CSS 处理, 这里只要少量)
          const padX = 2
          const padY = 1
          const bgW = contentW + padX * 2
          const bgH = contentH + padY * 2

          // 清除旧 bgRect (可能有多个)
          const oldRects = label.querySelectorAll('rect[data-bg-rect="true"]')
          oldRects.forEach(r => r.remove())

          // 创建 SVG rect 作为白色背景
          const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')

          // 把 bgRect 插到 g.label 下 (而不是 g.edgeLabel), 这样可以用 local (0,0) = fo 左上角
          if (innerLabelG) {
            // 删掉旧的
            const innerOld = innerLabelG.querySelectorAll('rect[data-bg-rect="true"]')
            innerOld.forEach(r => r.remove())
            bgRect.setAttribute('x', -padX)
            bgRect.setAttribute('y', -padY)
            bgRect.setAttribute('width', bgW)
            bgRect.setAttribute('height', bgH)
            bgRect.setAttribute('rx', '2')
            bgRect.setAttribute('ry', '2')
            bgRect.setAttribute('fill', '#ffffff')
            bgRect.setAttribute('fill-opacity', '1')
            bgRect.setAttribute('data-bg-rect', 'true')
            bgRect.style.setProperty('fill', '#ffffff', 'important')
            bgRect.style.setProperty('fill-opacity', '1', 'important')
            bgRect.style.setProperty('opacity', '1', 'important')
            bgRect.style.setProperty('display', 'block', 'important')
            bgRect.style.setProperty('visibility', 'visible', 'important')
            bgRect.style.setProperty('stroke', 'none', 'important')
            // 插到 innerLabelG 的最前面 (作为 background)
            const firstChild = innerLabelG.firstChild
            if (firstChild) {
              innerLabelG.insertBefore(bgRect, firstChild)
            } else {
              innerLabelG.appendChild(bgRect)
            }
          } else {
            // fallback: 插到 g.edgeLabel, 中心对齐
            bgRect.setAttribute('x', -bgW / 2)
            bgRect.setAttribute('y', -bgH / 2)
            bgRect.setAttribute('width', bgW)
            bgRect.setAttribute('height', bgH)
            bgRect.setAttribute('fill', '#ffffff')
            bgRect.setAttribute('fill-opacity', '1')
            bgRect.setAttribute('data-bg-rect', 'true')
            bgRect.style.setProperty('fill', '#ffffff', 'important')
            bgRect.style.setProperty('fill-opacity', '1', 'important')
            bgRect.style.setProperty('opacity', '1', 'important')
            bgRect.style.setProperty('display', 'block', 'important')
            bgRect.style.setProperty('visibility', 'visible', 'important')
            bgRect.style.setProperty('stroke', 'none', 'important')
            const firstChild = label.firstChild
            if (firstChild) {
              label.insertBefore(bgRect, firstChild)
            } else {
              label.appendChild(bgRect)
            }
          }
        } catch (e) {
          console.warn('创建背景 rect 失败:', e)
        }
      })

      const rootGroup = labelParent?.parentElement
      const allEdgePathsInRoot = rootGroup?.querySelectorAll('.edgePath path, path.flowchart-link')

      let correspondingPath = null
      if (allEdgePathsInRoot && allEdgePathsInRoot.length > index) {
        correspondingPath = allEdgePathsInRoot[index]
      }

      if (!correspondingPath) {
        console.warn(`标签 ${index} 没有找到对应的连线path`)
        return
      }

      const pathLength = correspondingPath.getTotalLength()
      const startPoint = correspondingPath.getPointAtLength(0)
      const endPoint = correspondingPath.getPointAtLength(pathLength)

      const sampleCount = 50
      let nearestPoint = null
      let nearestDist = Infinity

      for (let i = 0; i <= sampleCount; i++) {
        const ratio = i / sampleCount
        const point = correspondingPath.getPointAtLength(pathLength * ratio)
        const dist = Math.hypot(point.x - labelCenterX, point.y - labelCenterY)
        if (dist < nearestDist) {
          nearestDist = dist
          nearestPoint = point
        }
      }

      const distToStart = Math.hypot(startPoint.x - labelCenterX, startPoint.y - labelCenterY)
      const distToEnd = Math.hypot(endPoint.x - labelCenterX, endPoint.y - labelCenterY)

      const useNearestPoint = nearestDist < Math.min(distToStart, distToEnd) ? nearestPoint : (distToStart < distToEnd ? startPoint : endPoint)

      const tailLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      tailLine.setAttribute('x1', labelCenterX.toFixed(2))
      tailLine.setAttribute('y1', labelCenterY.toFixed(2))
      tailLine.setAttribute('x2', useNearestPoint.x.toFixed(2))
      tailLine.setAttribute('y2', useNearestPoint.y.toFixed(2))
      tailLine.setAttribute('stroke', '#333333')
      tailLine.setAttribute('stroke-width', '1.5')
      tailLine.setAttribute('stroke-dasharray', '4,3')
      tailLine.setAttribute('opacity', '0.8')
      tailLine.setAttribute('data-trailing-line', 'true')
      svg.appendChild(tailLine)

      const endMarker = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      endMarker.setAttribute('cx', useNearestPoint.x.toFixed(2))
      endMarker.setAttribute('cy', useNearestPoint.y.toFixed(2))
      endMarker.setAttribute('r', '3')
      endMarker.setAttribute('fill', '#333333')
      endMarker.setAttribute('opacity', '0.8')
      endMarker.setAttribute('data-trailing-marker', 'true')
      svg.appendChild(endMarker)
    })

    // 使用 CSS 类控制拖尾线显示/隐藏
    if (hideTails) {
      svg.classList.add('hide-tails')
    }
  }

  const addClickToClearHighlight = (svg, selectedElements) => {
    const onClick = (e) => {
      // [P1-B 2026-08-03] 拖动守卫: 与 annotationOverlay onSvgClick 的 isDraggingState 守卫对齐.
      //   之前: 用户拖动图表 (panning) 后浏览器仍 fire click 事件, 触发 clearHighlight 误清高亮.
      //   现在: mousedown 记录起点 (onMouseDown), click 时若位移 > 5px 视为拖动, 跳过 clear.
      //   阈值 5px 与常规 click 抖动留出余量, 不影响真实空白点击清高亮 (D5b 测试覆盖).
      if (_mouseDownPos) {
        const dx = e.clientX - _mouseDownPos.x
        const dy = e.clientY - _mouseDownPos.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        _mouseDownPos = null
        if (dist > 5) {
          diag.recordStepMeta('useTooltipClearSkip', {
            reason: 'drag', dist: Math.round(dist)
          })
          return
        }
      }
      const target = e.target
      const isNode = target.closest('.node')
      const isEdgePath = target.closest('.edgePath') || target.classList.contains('flowchart-link')
      const isEdgeLabel = target.closest('.edgeLabel')

      if (!isNode && !isEdgePath && !isEdgeLabel) {
        clearHighlight(selectedElements)
      }
    }
    const onMouseDown = (e) => {
      _mouseDownPos = { x: e.clientX, y: e.clientY }
    }
    // [FIX 2026-08-03] 监听器从 <svg> 改为外层 .draggable-area 容器
    //   之前绑 svg 时, 点击 svg 外部 (背景可拖拽区域) 事件不冒泡到 svg, clearHighlight 不触发
    //   用户报告: 点击背景/可拖拽区域, highlighted 元素不取消; 只有 svg 内点击才取消
    //   容器链 fallback 兼容单测 (svg 无 .draggable-area 祖先时退回 svg 自身)
    const container = svg.closest('.draggable-area') || svg.closest('.mermaid-content') || svg
    addListener(container, 'click', onClick)
    addListener(container, 'mousedown', onMouseDown)
  }

  const addMouseOverTooltips = (svg, relationDescriptions, diagramType, hideTails = false, annotationFilter = []) => {
    if (!svg) return

    // 先清理本实例上一次的监听器和装饰元素（不跨实例）
    cleanup()

    const tooltip = createTooltipElement()
    const selectedElements = createSelectionState()
    const edgeLabels = getEdgeLabels(svg)
    _currentSvg = svg

    // [OK] 纯 CSS 方案：不再需要 JavaScript 设置背景
    // setLabelBackground(edgeLabels)

    const { pathToRelationMap, realEdgePaths } = matchPathsToRelations(svg, edgeLabels, relationDescriptions)

    edgeLabels.forEach((label, index) => {
      setupLabelEvents(label, index, tooltip, relationDescriptions, pathToRelationMap, edgeLabels, selectedElements, svg, realEdgePaths, annotationFilter)
    })

    realEdgePaths.forEach((edgePathInfo) => {
      setupPathEvents(edgePathInfo.path, tooltip, pathToRelationMap, edgeLabels, selectedElements, svg, annotationFilter)
    })

    addTrailingDottedLines(svg, edgeLabels, diagramType, hideTails)

    addClickToClearHighlight(svg, selectedElements)
  }

  // 清理本实例注册的所有事件监听器 + 当前 svg 上的装饰元素
  // 不清理 tooltip DOM 元素（fullscreen 切换需要复用）
  // 不影响其他 MermaidComponent 实例
  const cleanup = () => {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns = []
    if (_currentSvg) {
      _currentSvg.querySelectorAll('[data-trailing-line], [data-trailing-marker]').forEach(el => el.remove())
    }
    _currentSvg = null
    // [P0-B] 清理时同步重置 diag highlight 状态 — chartType 切换 / 组件卸载后,
    //   旧 selectedElements 闭包失效, diag._highlightState 不应再报告 hasHighlight=true.
    //   D10 测试断言 chartType 切换后 highlight 干净 (DOM + 状态双重断言).
    diag.setHighlightState(null)
    _mouseDownPos = null
  }

  return {
    addMouseOverTooltips,
    cleanup,
    // [v34 双向支持] 导出供单测覆盖 (useTooltip.spec.js)
    formatTooltipText,
    // [P0-B 2026-08-03] 暴露 highlight 状态查询入口 (供 useDiagnostics → window.__archPage.mermaid.highlight)
    //   返回 { hasHighlight, path, label, sourceNode, targetNode } 纯数据快照, 不含 DOM 引用.
    getHighlightState: () => diag.getHighlightState()
  }
}