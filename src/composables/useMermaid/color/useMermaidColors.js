import { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR } from '@/constants/diagram'

export { COLOR_SCHEMES, DEFAULT_COLOR, DEFAULT_LINK_COLOR }

export function useMermaidColors() {

  const getColorScheme = (schemeName) => {
    return COLOR_SCHEMES[schemeName] || COLOR_SCHEMES.default
  }

  const buildColorMap = (nodeColorMappings, objectToModuleMap, colorGroupBy, colorSchemes, customColors = {}) => {
    const colors = colorSchemes
    const colorMap = new Map()
    const uniqueGroups = new Set()

    console.log('[buildColorMap] customColors received:', customColors)

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
        uniqueGroups.add(groupKey)
      }
    })

    let colorIndex = 0
    uniqueGroups.forEach(group => {
      const useCustom = !!customColors[group]
      const assigned = useCustom ? customColors[group] : colors[colorIndex % colors.length]
      if (useCustom) {
        colorMap.set(group, assigned)
      } else {
        colorMap.set(group, assigned)
        colorIndex++
      }
    })

    return colorMap
  }

  /**
   * [FOLD 2026-08-09] 折叠视图下从全量 BO 节点构建颜色映射。
   *
   * 背景: 折叠视图 (领域/子领域/服务模块折叠为聚合节点) 时, syntax 层不产生
   *   nodeColorMappings (空数组), 原 buildColorMap 依赖它 → colorMap 为空 →
   *   updateCollapseNodeColors 全灰 + buildColorLegendData 无映射色。
   * 本函数直接遍历 diagramData.nodes (折叠视图下仍含全量 BO 节点, 带
   *   domain/subDomain/serviceModuleName 字段), 按 colorGroupBy 推导分组键,
   *   与 buildColorLegendData / updateCollapseNodeColors 的取色键同源。
   *
   * @param {Array} nodes - diagramData.nodes (全量 BO 节点)
   * @param {string} colorGroupBy - domain | subDomain | serviceModule
   * @param {Object} colorSchemes - COLOR_SCHEMES[colorScheme]
   * @param {Object} customColors - 用户自定义颜色 { groupKey: color }
   * @returns {Map<string,string>} groupKey -> color
   */
  const buildColorMapFromNodes = (nodes, colorGroupBy, colorSchemes, customColors = {}) => {
    const colorMap = new Map()
    const uniqueGroups = new Set()
    ;(nodes || []).forEach(node => {
      let groupKey
      if (colorGroupBy === 'serviceModule') {
        groupKey = node.serviceModuleName || node.serviceModule || node.name
      } else if (colorGroupBy === 'subDomain') {
        groupKey = node.subDomain
      } else {
        groupKey = node.domain
      }
      if (groupKey) uniqueGroups.add(groupKey)
    })
    let colorIndex = 0
    uniqueGroups.forEach(group => {
      const useCustom = !!customColors[group]
      const assigned = useCustom ? customColors[group] : colorSchemes[colorIndex % colorSchemes.length]
      colorMap.set(group, assigned)
      if (!useCustom) colorIndex++
    })
    return colorMap
  }

  const updateNodeColors = (svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, options = {}) => {
    // [FIX 2026-08-02 v5] 回到原方案: 区分中心范围时, 中心节点 fill = centerScopeColor (指定的颜色)
    //   v2 曾改为"分组色 + 粗虚线边框", 用户反馈虚线区分不明显, 改回用颜色区分。
    //   非中心节点仍用分组色 (切换颜色分组/配色时联动变色)。
    const centerScopeHighlight = options.centerScopeHighlight !== false  // 默认 true
    const centerScopeSet = new Set(options.centerScope || [])
    const centerScopeColor = options.centerScopeColor || '#808080'

    nodeColorMappings.forEach(mapping => {
      const moduleInfo = objectToModuleMap.get(mapping.nodeCode) || objectToModuleMap.get(mapping.nodeName)
      if (moduleInfo) {
        let groupKey
        if (colorGroupBy === 'serviceModule') {
          groupKey = moduleInfo.serviceModuleName || moduleInfo.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          groupKey = moduleInfo.subDomain
        } else {
          groupKey = moduleInfo.domain
        }
        const isCenter = centerScopeHighlight && (centerScopeSet.has(mapping.nodeCode) || centerScopeSet.has(mapping.nodeName))
        const groupColor = colorMap.get(groupKey) || DEFAULT_COLOR
        // [v5] 中心节点 fill 用指定颜色 centerScopeColor, 非中心节点用分组色
        const newColor = isCenter ? centerScopeColor : groupColor

        // [FIX 2026-07-31] Mermaid 11.13.0 SVG g.node 元素的 id 格式为 `flowchart-{nodeId}-{counter}`
        // (例如 mapping.nodeId='N40' → SVG id='flowchart-N40-37')，旧的 `#${nodeId}` 选择器无法匹配。
        // 用属性前缀选择器 `g.node[id^="flowchart-{nodeId}-"]` 兼容 mermaid v11+ 格式。
        // [FIX 2026-07-31 v2] useSvgProcessor.addNodeCodeAttributes 把 BO code 写到 `data-code` 属性
        //   (不是 `data-id`!), 之前选择器 `[data-id="..."]` 用错了属性名 → 切换 colorGroupBy 时
        //   只 fallback 命中, 仍可能漏匹配某些节点。改用 `[data-code="BO_CODE"]` 精准命中。
        //   保留 mermaid id 前缀兜底以兼容未设置 data-code 的场景。
        const nodeElement = svg.querySelector(
          `#${mapping.nodeId} rect, [data-code="${mapping.nodeCode}"] rect, [data-id="${mapping.nodeId}"] rect, g.node[id^="flowchart-${mapping.nodeId}-"] rect`
        )
        if (nodeElement) {
          // [FIX 2026-08-02] 先清除初始渲染 renderMermaid 留下的 `fill ... !important` 内联样式
          //   (旧版 renderMermaid 对中心范围节点用 style.setProperty('fill', csColor, 'important')),
          //   否则切 centerScopeHighlight=false 后 !important 会压制这里的新 fill, 视觉不更新。
          nodeElement.style.removeProperty('fill')
          nodeElement.setAttribute('fill', newColor)
          // [FIX 2026-08-02 v4] 必须用 !important 设置内联 fill:
          //   mermaid 语法层 `classDef default fill:#fafafa` 会生成 SVG 内部 CSS (如 `.default > rect { fill:#fafafa !important }`),
          //   且节点 class 含 "default"。普通 style.fill (无 !important) 会被该 classDef 的 !important 规则压制
          //   → computedStyle 变 #fafafa 灰白 (用户看到"切色后节点全灰", 连线正常因为 linkStyle 无此压制)。
          //   初始渲染可见是因为 mermaid style 指令自带 !important (style="fill:#... !important")。
          //   这里用 setProperty(..., 'important') 与初始渲染对齐, 保证视觉更新。
          nodeElement.style.setProperty('fill', newColor, 'important')

          // [FIX 2026-08-02 v5] 边框统一恢复默认 (去掉中心范围的粗虚线边框方案)
          nodeElement.style.removeProperty('stroke')
          nodeElement.style.removeProperty('stroke-width')
          nodeElement.style.removeProperty('stroke-dasharray')
          nodeElement.setAttribute('stroke', '#333333')
          nodeElement.setAttribute('stroke-width', '2')
          nodeElement.removeAttribute('stroke-dasharray')
        }

        // 图例按分组色记录 (中心节点仅视觉 fill 被 centerScopeColor 覆盖, 分组色不随中心变灰)
        mapping.color = groupColor
      }
    })
  }

  const updateLinkColors = (svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, options = {}) => {
    // [FIX 2026-08-02 v6] 增量更新连线颜色也遵循中心范围规则 (与语法层生成一致):
    //   双中心 -> centerScopeColor 灰 / 一中心一非中心 -> 非中心色 / 双非中心(或不区分) -> 黑色
    const centerScopeHighlight = options.centerScopeHighlight !== false  // 默认 true
    const centerScopeSet = new Set(options.centerScope || [])
    const centerScopeColor = options.centerScopeColor || '#808080'

    linkColorMappings.forEach(mapping => {
      const sourceMapping = nodeColorMappings.find(n => n.nodeId === mapping.sourceId)
      const targetMapping = nodeColorMappings.find(n => n.nodeId === mapping.targetId)
      const sourceModule = objectToModuleMap.get(sourceMapping?.nodeCode)
      const targetModule = objectToModuleMap.get(targetMapping?.nodeCode)

      if (sourceModule && targetModule) {
        let sourceGroupKey, targetGroupKey
        if (colorGroupBy === 'serviceModule') {
          sourceGroupKey = sourceModule.serviceModuleName || sourceModule.serviceModule
          targetGroupKey = targetModule.serviceModuleName || targetModule.serviceModule
        } else if (colorGroupBy === 'subDomain') {
          sourceGroupKey = sourceModule.subDomain
          targetGroupKey = targetModule.subDomain
        } else {
          sourceGroupKey = sourceModule.domain
          targetGroupKey = targetModule.domain
        }

        const sourceGroupColor = colorMap.get(sourceGroupKey)
        const targetGroupColor = colorMap.get(targetGroupKey)

        const isSourceCenter = centerScopeHighlight && (centerScopeSet.has(sourceMapping.nodeCode) || centerScopeSet.has(sourceMapping.nodeName))
        const isTargetCenter = centerScopeHighlight && (centerScopeSet.has(targetMapping.nodeCode) || centerScopeSet.has(targetMapping.nodeName))

        let newColor
        if (isSourceCenter && isTargetCenter) {
          newColor = centerScopeColor
        } else if (isSourceCenter) {
          newColor = targetGroupColor || sourceGroupColor || DEFAULT_LINK_COLOR
        } else if (isTargetCenter) {
          newColor = sourceGroupColor || targetGroupColor || DEFAULT_LINK_COLOR
        } else {
          newColor = '#000000'
        }

        // [FIX 2026-07-31] Mermaid 11.13.0 把 edge path 直接放在 g.edgePaths 下，不再用 g.edgePath 包裹
        // 旧选择器 `.flowchart-link path, .edgePath path` 返回 0 个元素。
        // 增加 `.edgePaths > path` 兼容 mermaid v11+ (路径作为 edgePaths 直接子元素)。
        const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path, .edgePaths > path')
        if (paths[mapping.index]) {
          paths[mapping.index].setAttribute('stroke', newColor)
          paths[mapping.index].style.stroke = newColor
        }

        mapping.color = newColor
      }
    })
  }

  const updateColorsOnly = (
    svg,
    nodeColorMappings,
    linkColorMappings,
    objectToModuleMap,
    data,
    colorGroupBy
  ) => {
    if (!svg) return false

    const currentColorGroupBy = colorGroupBy
    const colorSchemes = getColorScheme(data.colorScheme)

    const colorMap = buildColorMap(
      nodeColorMappings,
      objectToModuleMap,
      currentColorGroupBy,
      colorSchemes,
      data.customColors || {}
    )

    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap, {
      centerScopeHighlight: data.centerScopeHighlight,
      centerScope: data.centerScope || [],
      centerScopeColor: data.centerScopeColor || '#808080'
    })

    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, currentColorGroupBy, colorMap, {
      centerScopeHighlight: data.centerScopeHighlight,
      centerScope: data.centerScope || [],
      centerScopeColor: data.centerScopeColor || '#808080'
    })

    return true
  }

  // [INC 2026-08-09] 增量更新「折叠视图」的折叠节点颜色。
  //   折叠视图: 领域/子领域/服务模块折叠为 COLLAPSE_<id> 聚合节点 (g.node.collapseNode,
  //   带 data-container-code), nodeColorMappings 为空, 原 updateNodeColors 无法着色 →
  //   切换 colorGroupBy 时 MermaidComponent.updateColorsOnly 只能 return false → 回退
  //   renderMermaid 全量重载 (闪 loading + 重置展开态)。
  //   本函数基于「分组上下文 (domainName/subDomainName/serviceModuleName) + groupColorMap
  //   (与图表同源)」, 按当前 colorGroupBy 重算每个折叠节点颜色, 直接改 SVG rect fill,
  //   实现增量更新, 与语法层 applyUpliftNodeColors 取色规则一致:
  //   - 中心范围折叠节点 → centerScopeColor
  //   - 否则按 colorGroupBy 取分组 key → groupColorMap[key]
  //   - 取不到 (折叠层级 > 颜色分组层级, 如"按服务模块"折叠了子领域) → 中性灰 #fafafa (同 classDef default)
  const updateCollapseNodeColors = (svg, collapseContextMap, colorGroupBy, colorMap, options = {}) => {
    if (!svg) return
    const centerScopeHighlight = options.centerScopeHighlight !== false // 默认 true
    const centerScopeColor = options.centerScopeColor || '#808080'
    const centerScopeMarkers = options.centerScopeMarkers || {}

    svg.querySelectorAll('g.node[id*="COLLAPSE_"], g.node.collapseNode').forEach((el) => {
      const code = el.getAttribute('data-container-code')
      if (!code) return
      const ctx = collapseContextMap.get(code)
      if (!ctx) return
      const rect = el.querySelector('rect')
      if (!rect) return

      // 中心范围判定 (与 useGroupDisplay 中心判定一致, 按折叠节点层级查对应 markers)
      // [FIX 2026-08-09 v3] subDomains/domains 标记的 value 是布尔 (hasCenter),
      //   且【所有】分组都会写入 map (markers.subDomains.set(name, hasCenter) /
      //   markers.domains.set(name, hasCenter)). 用 .has() 只查 key 是否存在 →
      //   返回 true 与 value 无关 → 所有子领域/领域都被误判为中心范围 → 折叠节点全染 centerScopeColor.
      //   必须 .get()===true 校验布尔值. serviceModules 只写入中心范围 SM (value 恒 true), .has() 无碍.
      let isCenter = false
      if (centerScopeHighlight) {
        if (ctx.groupType === 'serviceModule') {
          isCenter = !!centerScopeMarkers.serviceModules?.has(ctx.serviceModuleName)
            || !!centerScopeMarkers.serviceModules?.has(code)
        } else if (ctx.groupType === 'subDomain') {
          isCenter = centerScopeMarkers.subDomains?.get(ctx.subDomainName) === true
            || centerScopeMarkers.subDomains?.get(code) === true
        } else if (ctx.groupType === 'domain') {
          isCenter = centerScopeMarkers.domains?.get(ctx.domainName) === true
            || centerScopeMarkers.domains?.get(code) === true
        }
      }
      if (isCenter) {
        rect.style.setProperty('fill', centerScopeColor, 'important')
        return
      }

      let key
      if (colorGroupBy === 'serviceModule') key = ctx.serviceModuleName || ctx.title
      else if (colorGroupBy === 'subDomain') key = ctx.subDomainName || ctx.title
      else key = ctx.domainName || ctx.title

      // [FIX 2026-08-09] colorMap 键须与全量渲染/展开增量一致 (serviceModuleName/domain/subDomain),
      //   不能直接用 colorize 的 groupColorMap (其 serviceModule 键是 BO 的 name, 键不一致 → 折叠节点全灰)。
      //   colorMap 为 Map 或普通对象, 兼容两者.
      const getColor = (m, k) => (m && typeof m.get === 'function' ? m.get(k) : m?.[k])
      const color = (key && getColor(colorMap, key)) || '#fafafa'
      rect.style.setProperty('fill', color, 'important')
    })
  }

  return {
    COLOR_SCHEMES,
    DEFAULT_COLOR,
    DEFAULT_LINK_COLOR,
    getColorScheme,
    buildColorMap,
    buildColorMapFromNodes,
    updateNodeColors,
    updateLinkColors,
    updateColorsOnly,
    updateCollapseNodeColors
  }
}
