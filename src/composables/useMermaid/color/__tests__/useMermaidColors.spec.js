/**
 * useMermaidColors 单测 (v32 复盘回归保护 - 2026-06-11)
 *
 * 覆盖:
 * - getColorScheme (3 测试): 7 个内置 scheme / 未知 fallback / 空值 fallback
 * - buildColorMap (4 测试): 3 种 groupBy / customColors 覆盖 / nodeName 兜底 / 颜色循环
 * - updateLinkColors (4 测试): 同域 / 跨域 / source fallback target / DEFAULT_LINK_COLOR
 * - filterEnabledContainers (4 测试): 默认全保留 / disabled 过滤 / null 过滤 / 组合
 *
 * 总计: 15 个测试, ~120 行
 */
import { describe, it, expect } from 'vitest'
import { useMermaidColors } from '../useMermaidColors'
import { filterEnabledContainers, partitionContainersByEnabled } from '../../layouts/containerFilter'

describe('useMermaidColors - getColorScheme', () => {
  it('7 个内置 scheme 都能取到', () => {
    const { getColorScheme } = useMermaidColors()
    const schemes = ['default', 'vibrant', 'pastel', 'warm', 'cool', 'business', 'nature']
    schemes.forEach(name => {
      const scheme = getColorScheme(name)
      expect(scheme).toBeDefined()
      expect(Array.isArray(scheme)).toBe(true)
      expect(scheme.length).toBeGreaterThanOrEqual(8)
    })
  })

  it('未知 scheme 应 fallback 到 default', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('unknown-scheme')).toEqual(getColorScheme('default'))
  })

  it('空字符串 / null / undefined 都应 fallback', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('')).toEqual(getColorScheme('default'))
    expect(getColorScheme(null)).toEqual(getColorScheme('default'))
    expect(getColorScheme(undefined)).toEqual(getColorScheme('default'))
  })
})

describe('useMermaidColors - buildColorMap', () => {
  it('colorGroupBy=domain 时按 domain 分组, 相同 domain 合并', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务A' }],
      ['N3', { domain: '业务B' }]
    ])
    const nodeColorMappings = [
      { nodeCode: 'N1' },
      { nodeCode: 'N2' },
      { nodeCode: 'N3' }
    ]
    const colorMap = buildColorMap(
      nodeColorMappings, objectToModuleMap, 'domain',
      ['#FF0000', '#00FF00', '#0000FF'], {}
    )
    expect(colorMap.size).toBe(2)  // 业务A + 业务B
    expect(colorMap.get('业务A')).toBe('#FF0000')
    expect(colorMap.get('业务B')).toBe('#00FF00')
  })

  it('colorGroupBy=serviceModule 时按 serviceModuleName 分组', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { serviceModuleName: '订单模块' }],
      ['N2', { serviceModule: '支付模块' }]  // serviceModule 兜底
    ])
    const colorMap = buildColorMap(
      [{ nodeCode: 'N1' }, { nodeCode: 'N2' }], objectToModuleMap, 'serviceModule',
      ['#FF0000', '#00FF00'], {}
    )
    expect(colorMap.get('订单模块')).toBe('#FF0000')
    expect(colorMap.get('支付模块')).toBe('#00FF00')
  })

  it('customColors 覆盖默认 scheme 颜色', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([['N1', { domain: '业务A' }]])
    const colorMap = buildColorMap(
      [{ nodeCode: 'N1' }], objectToModuleMap, 'domain',
      ['#FF0000'], { '业务A': '#123456' }
    )
    expect(colorMap.get('业务A')).toBe('#123456')  // 自定义覆盖
  })

  it('颜色 index 超过 scheme 长度时循环', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map()
    const nodeColorMappings = []
    // 13 个分组, scheme 只有 2 色, 应循环
    for (let i = 0; i < 13; i++) {
      const code = `N${i}`
      objectToModuleMap.set(code, { domain: `域${i}` })
      nodeColorMappings.push({ nodeCode: code })
    }
    const colorMap = buildColorMap(
      nodeColorMappings, objectToModuleMap, 'domain',
      ['#FF0000', '#00FF00'], {}
    )
    expect(colorMap.size).toBe(13)
    // 第 13 个 (index=12) 应是 #FF0000 (12 % 2 = 0)
    expect(colorMap.get('域12')).toBe('#FF0000')
  })
})

describe('useMermaidColors - buildColorMapFromNodes (折叠视图颜色映射 2026-08-09)', () => {
  it('colorGroupBy=subDomain 时按 subDomain 分组, 相同 subDomain 合并取同一色', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { domain: '供应链云', subDomain: '采购供应', serviceModuleName: '需求计划', code: 'MM01' },
      { domain: '供应链云', subDomain: '采购供应', serviceModuleName: '采购管理', code: 'MM02' },
      { domain: '供应链云', subDomain: '销售', serviceModuleName: '销售管理', code: 'SM01' }
    ]
    const colorMap = buildColorMapFromNodes(nodes, 'subDomain', ['#1890FF', '#52C41A'])
    expect(colorMap.size).toBe(2)
    expect(colorMap.get('采购供应')).toBe('#1890FF')
    expect(colorMap.get('销售')).toBe('#52C41A')
  })

  it('colorGroupBy=domain 时按 domain 分组', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { domain: '供应链云', subDomain: '采购供应', code: 'MM01' },
      { domain: '供应链云', subDomain: '销售', code: 'SM01' },
      { domain: '制造云', subDomain: '生产', code: 'MF01' }
    ]
    const colorMap = buildColorMapFromNodes(nodes, 'domain', ['#FF0000', '#00FF00'])
    expect(colorMap.size).toBe(2)
    expect(colorMap.get('供应链云')).toBe('#FF0000')
    expect(colorMap.get('制造云')).toBe('#00FF00')
  })

  it('colorGroupBy=serviceModule 时 serviceModuleName 优先, serviceModule/name 兜底', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { domain: '供应链云', subDomain: '采购供应', serviceModuleName: '需求计划', code: 'N1' },
      { domain: '供应链云', subDomain: '采购供应', serviceModule: '采购管理', code: 'N2' }, // serviceModule 兜底
      { domain: '供应链云', subDomain: '采购供应', name: '销售管理', code: 'N3' }            // name 兜底
    ]
    const colorMap = buildColorMapFromNodes(nodes, 'serviceModule', ['#AA0000', '#00AA00', '#0000AA'])
    expect(colorMap.get('需求计划')).toBe('#AA0000')
    expect(colorMap.get('采购管理')).toBe('#00AA00')
    expect(colorMap.get('销售管理')).toBe('#0000AA')
  })

  // [FIX 2026-08-11 colorIndex-drift] 自定义色覆盖不应推移其它分组默认色索引.
  //   旧行为: 被覆盖分组不占用 index → 后续分组索引整体前移 (用户反馈: 改供应链云色,
  //   制作云 从绿[1] 变蓝[0]). 新行为: 默认色按分组位置索引分配, 与自定义色无关.
  it('customColors 覆盖默认 scheme 颜色, 且不推移其它分组默认色', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { domain: '供应链云', subDomain: '采购供应', code: 'A' },
      { domain: '供应链云', subDomain: '销售', code: 'B' }
    ]
    // 采购供应用自定义色 (#123456), 销售按位置索引(1)取 #00FF00, 不被推移.
    const colorMap = buildColorMapFromNodes(nodes, 'subDomain', ['#FF0000', '#00FF00'], {
      '采购供应': '#123456'
    })
    expect(colorMap.get('采购供应')).toBe('#123456')
    expect(colorMap.get('销售')).toBe('#00FF00')
  })

  it('颜色 index 超过 scheme 长度时循环', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = []
    for (let i = 0; i < 5; i++) {
      nodes.push({ domain: '域0', subDomain: `子域${i}` })
    }
    const colorMap = buildColorMapFromNodes(nodes, 'subDomain', ['#FF0000', '#00FF00'])
    // 5 个分组, scheme 只有 2 色; 第 5 个 (index=4) -> 4 % 2 = 0 -> #FF0000
    expect(colorMap.size).toBe(5)
    expect(colorMap.get('子域0')).toBe('#FF0000')
    expect(colorMap.get('子域4')).toBe('#FF0000')
    expect(colorMap.get('子域1')).toBe('#00FF00')
  })

  it('缺 groupKey 的节点被跳过', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { name: 'no-subDomain', code: 'X' },
      { domain: '域0', subDomain: '子域A' }
    ]
    const colorMap = buildColorMapFromNodes(nodes, 'subDomain', ['#FF0000'])
    expect(colorMap.size).toBe(1)
    expect(colorMap.get('子域A')).toBe('#FF0000')
  })

  it('空 nodes / 空 scheme 时安全返回空 Map', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    expect(buildColorMapFromNodes([], 'domain', ['#FF0000']).size).toBe(0)
    expect(buildColorMapFromNodes(null, 'domain', ['#FF0000']).size).toBe(0)
    expect(buildColorMapFromNodes([{ domain: 'A' }], 'domain', []).size).toBe(1)
  })

  // [FIX 2026-08-13 范围外节点中性 bug] 增量变色必须用 data.nodes 全量 BO 集构建 colorMap,
  //   覆盖所有领域 (含折叠/范围外 BO 领域), 否则范围外聚合节点回退中性灰.
  //   这里模拟: data.nodes 含范围内(采购供应) + 范围外(采购云其它子域) BO,
  //   nodeColorMappings 只含范围内 BO (范围外 BO 被折叠隐藏) 的场景 — 必须包含采购云领域.
  it('data.nodes 全量推导包含范围外领域 (修复范围外节点中性 bug)', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const dataNodes = [
      { code: 'PS01', domain: '采购云', subDomain: '采购供应', serviceModuleName: '采购管理' },
      { code: 'PS02', domain: '采购云', subDomain: '采购供应', serviceModuleName: '采购管理' },
      { code: 'OUT01', domain: '采购云', subDomain: '外部采购', serviceModuleName: '询比价' } // 范围外, 折叠隐藏
    ]
    // 仅模拟 nodeColorMappings 覆盖范围内节点 → 但构建源是完整 dataNodes → 采购云领域必在 map
    const colorMap = buildColorMapFromNodes(dataNodes, 'domain', ['#111111'])
    expect(colorMap.has('采购云')).toBe(true)
    expect(colorMap.get('采购云')).toBe('#111111')
    // subDomain 分组同样覆盖范围外子域
    const sdMap = buildColorMapFromNodes(dataNodes, 'subDomain', ['#222222'])
    expect(sdMap.has('外部采购')).toBe(true)
  })

  // objectToModuleMap 优先推导分组键 (与全量渲染 colorMap 同源), node 字段兜底.
  it('objectToModuleMap 优先推导分组键, node 字段兜底', () => {
    const { buildColorMapFromNodes } = useMermaidColors()
    const nodes = [
      { code: 'A', domain: '错误域', subDomain: 'X' },
      { code: 'B', domain: '制造云', subDomain: 'Y' }
    ]
    const o2m = new Map([['A', { domain: '供应链云', subDomain: '采购供应' }]])
    const colorMap = buildColorMapFromNodes(nodes, 'domain', ['#FF0000', '#00FF00'], {}, o2m)
    // A 用 objectToModuleMap 的 domain, B 用 node.domain
    expect(colorMap.get('供应链云')).toBe('#FF0000')
    expect(colorMap.get('制造云')).toBe('#00FF00')
    expect(colorMap.has('错误域')).toBe(false)
  })
})

describe('useMermaidColors - updateLinkColors', () => {
  // 用 happy-dom 创建 mock svg
  function createMockSvg(numPaths = 1) {
    const paths = []
    for (let i = 0; i < numPaths; i++) {
      const path = {
        setAttribute: function(k, v) { this[k] = v },
        style: { stroke: '' }
      }
      paths.push(path)
    }
    return {
      querySelectorAll: (sel) => {
        if (sel.includes('.flowchart-link') || sel.includes('.edgePath')) {
          return paths
        }
        return []
      }
    }
  }

  // [FIX 2026-08-02 v6] 新连线规则 (与语法层生成一致):
  //   双非中心 / 不区分 -> 黑色; 双中心 -> centerScopeColor; 一中心一非中心 -> 非中心色
  const objectToModuleMap = new Map([
    ['N1', { domain: '业务A' }],
    ['N2', { domain: '业务B' }]
  ])
  const nodeColorMappings = [
    { nodeId: 'id1', nodeCode: 'N1', nodeName: '对象1' },
    { nodeId: 'id2', nodeCode: 'N2', nodeName: '对象2' }
  ]
  const linkColorMappings = [{ sourceId: 'id1', targetId: 'id2', index: 0 }]
  const colorMap = new Map([
    ['业务A', '#FF0000'],
    ['业务B', '#00FF00']
  ])

  it('双非中心连线 (默认) -> 黑色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#000000')
  })

  it('双中心连线 -> centerScopeColor 灰', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScope: ['N1', 'N2'],
      centerScopeColor: '#808080'
    })
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#808080')
  })

  it('一中心一非中心连线 -> 非中心节点颜色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    // 源 N1 是中心, 目标 N2 非中心 -> 用 N2 的域色 #00FF00
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScope: ['N1'],
      centerScopeColor: '#808080'
    })
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#00FF00')
  })

  it('不区分中心范围 (centerScopeHighlight=false) -> 黑色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: false,
      centerScope: ['N1', 'N2'],
      centerScopeColor: '#808080'
    })
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#000000')
  })

  it('path index 越界时优雅降级 (不抛错)', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)  // 只有 1 条 path
    const linkColorMappingsOverflow = [{
      sourceId: 'id1', targetId: 'id2', index: 999  // 越界
    }]
    expect(() => {
      updateLinkColors(svg, linkColorMappingsOverflow, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    }).not.toThrow()
  })
})

describe('useMermaidColors - updateLinkColors 容器/聚合连线增量变色 (2026-08-11)', () => {
  // 用户场景: 折叠视图 (nodeColorMappings 为空), 改"供应链云"色为红后,
  //   从中心范围 (供应链计划, SCP) 到 采购供应 的容器连线应联动为红.
  function createMockSvg(numPaths = 1) {
    const paths = []
    for (let i = 0; i < numPaths; i++) {
      paths.push({
        setAttribute: function(k, v) { this[k] = v },
        style: { stroke: '' }
      })
    }
    return {
      querySelectorAll: (sel) => {
        if (sel.includes('.flowchart-link') || sel.includes('.edgePath')) return paths
        return []
      }
    }
  }

  const collapseNodeMap = new Map([
    ['COLLAPSE_SCP', { code: 'SCP', groupType: 'subDomain', domainName: '供应链云', subDomainName: '供应链计划', serviceModuleName: '' }],
    ['COLLAPSE_CGY', { code: 'CGY', groupType: 'subDomain', domainName: '供应链云', subDomainName: '采购供应', serviceModuleName: '' }]
  ])
  // 供应链云 改为红 (原蓝), 按 domain 分组 → 采购供应归属 供应链云 → 连线应为红
  const colorMap = new Map([['供应链云', '#FF0000']])
  const centerScopeMarkers = { subDomains: new Map([['供应链计划', true]]) }
  const linkColorMappings = [{ sourceId: 'COLLAPSE_SCP', targetId: 'COLLAPSE_CGY', index: 0 }]
  const emptyNodeColorMappings = []
  const emptyObjectToModuleMap = new Map()

  it('折叠视图 nodeColorMappings 为空时, 中心→非中心容器连线取非中心端分组色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    updateLinkColors(svg, linkColorMappings, emptyNodeColorMappings, emptyObjectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: true,
      centerScope: [],
      centerScopeColor: '#808080',
      collapseNodeMap,
      centerScopeMarkers
    })
    // 源 (供应链计划) 中心, 目标 (采购供应) 非中心 → 用目标分组色 = 供应链云红
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#FF0000')
  })

  it('双非中心容器连线 (centerScopeHighlight=false) -> 黑色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    updateLinkColors(svg, linkColorMappings, emptyNodeColorMappings, emptyObjectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: false,
      centerScope: [],
      centerScopeColor: '#808080',
      collapseNodeMap,
      centerScopeMarkers
    })
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#000000')
  })

  it('解析不到任何端点 (无 collapseNodeMap) 时跳过, 不抛错', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    expect(() => {
      updateLinkColors(svg, linkColorMappings, emptyNodeColorMappings, emptyObjectToModuleMap, 'domain', colorMap, {
        centerScopeHighlight: true,
        centerScope: [],
        centerScopeColor: '#808080'
        // 无 collapseNodeMap → 两端解析不到 → 跳过
      })
    }).not.toThrow()
  })
})

describe('useMermaidColors - updateNodeColors (中心范围"分组色+边框" 2026-08-02)', () => {
  function createMockRect() {
    // [FIX 2026-08-02 v4] updateNodeColors 改用 style.setProperty(fill, color, 'important')
    //   覆盖 mermaid classDef default 生成的 !important 规则, mock 需提供 setProperty
    return {
      style: {
        fill: '',
        removeProperty: () => {},
        setProperty: function(k, v) { this.fill = v }
      },
      setAttribute: function(k, v) { this[k] = v },
      removeAttribute: function(k) { delete this[k] },
      getAttribute: function(k) { return this[k] }
    }
  }

  it('中心范围节点: fill=centerScopeColor (指定颜色) + 默认边框', () => {
    const { updateNodeColors } = useMermaidColors()
    const rect = createMockRect()
    const svg = { querySelector: () => rect }
    const objectToModuleMap = new Map([['N1', { domain: '业务A' }]])
    const nodeColorMappings = [{ nodeCode: 'N1', nodeName: 'N1' }]
    const colorMap = new Map([['业务A', '#1890FF']])
    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: true,
      centerScope: ['N1'],
      centerScopeColor: '#808080'
    })
    expect(rect.fill).toBe('#808080')       // 指定颜色 (原方案)
    expect(rect.style.fill).toBe('#808080')
    expect(rect.stroke).toBe('#333333')     // 默认边框, 不再用虚线
    expect(rect['stroke-width']).toBe('2')
    expect(rect['stroke-dasharray']).toBeUndefined()
  })

  it('centerScopeHighlight=false: 全部节点分组色 + 恢复默认边框', () => {
    const { updateNodeColors } = useMermaidColors()
    const rect = createMockRect()
    const svg = { querySelector: () => rect }
    const objectToModuleMap = new Map([['N1', { domain: '业务A' }]])
    const nodeColorMappings = [{ nodeCode: 'N1', nodeName: 'N1' }]
    const colorMap = new Map([['业务A', '#52C41A']])
    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: false,
      centerScope: ['N1'],
      centerScopeColor: '#808080'
    })
    expect(rect.fill).toBe('#52C41A')
    expect(rect.stroke).toBe('#333333')
    expect(rect['stroke-width']).toBe('2')
    expect(rect['stroke-dasharray']).toBeUndefined()
  })

  it('非中心节点: 分组色 + 默认边框', () => {
    const { updateNodeColors } = useMermaidColors()
    const rect = createMockRect()
    const svg = { querySelector: () => rect }
    const objectToModuleMap = new Map([['N1', { domain: '业务A' }]])
    const nodeColorMappings = [{ nodeCode: 'N1', nodeName: 'N1' }]
    const colorMap = new Map([['业务A', '#FAAD14']])
    updateNodeColors(svg, nodeColorMappings, objectToModuleMap, 'domain', colorMap, {
      centerScopeHighlight: true,
      centerScope: ['OTHER'],   // N1 不在中心范围
      centerScopeColor: '#808080'
    })
    expect(rect.fill).toBe('#FAAD14')
    expect(rect.stroke).toBe('#333333')
    expect(rect['stroke-dasharray']).toBeUndefined()
  })
})

describe('useMermaidColors - updateCollapseNodeColors (折叠节点增量变色 2026-08-09)', () => {
  function createCollapseSvg(entries) {
    const nodes = entries.map(e => {
      const rect = {
        style: { setProperty: function(k, v) { this.fill = v } },
        getAttribute: () => null
      }
      return {
        getAttribute: (k) => k === 'data-container-code' ? e.code : null,
        querySelector: (sel) => sel === 'rect' ? rect : null,
        __rect: rect
      }
    })
    return {
      querySelectorAll: (sel) => {
        if (sel.includes('COLLAPSE_') || sel.includes('collapseNode')) return nodes
        return []
      }
    }
  }

  it('按 serviceModule 分组: 折叠 SM 节点用 colorMap (键=serviceModuleName) 取色', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    // colorMap 键为 serviceModuleName (与 buildColorMap/全量渲染一致), 而非 BO name
    const colorMap = new Map([
      ['需求计划', '#1890FF'],
      ['采购管理', '#2FC25B']
    ])
    const collapseContextMap = new Map([
      ['DP', { groupType: 'serviceModule', serviceModuleName: '需求计划', title: '需求计划' }],
      ['CG', { groupType: 'serviceModule', serviceModuleName: '采购管理', title: '采购管理' }]
    ])
    const svg = createCollapseSvg([{ code: 'DP' }, { code: 'CG' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: false
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#1890FF')
    expect(svg.querySelectorAll('g.node.collapseNode')[1].__rect.style.fill).toBe('#2FC25B')
  })

  it('按 subDomain 分组: 折叠 SM 节点继承祖先 subDomain key 取色', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['供应链计划', '#FACC14']])
    // ctx.subDomainName 由祖先上下文传播填充 (折叠 SM + 按 subDomain 分组)
    const collapseContextMap = new Map([
      ['DP', { groupType: 'serviceModule', serviceModuleName: '需求计划', subDomainName: '供应链计划', domainName: '供应链云', title: '需求计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'DP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'subDomain', colorMap, {
      centerScopeHighlight: false
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#FACC14')
  })

  it('取不到颜色时回退中性灰 #fafafa (折叠层级 > 分组层级)', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([])
    const collapseContextMap = new Map([
      ['SCP', { groupType: 'subDomain', subDomainName: '供应链计划', title: '供应链计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'SCP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: false
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#fafafa')
  })

  it('中心范围折叠节点保持 centerScopeColor (完全包含对象范围)', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['需求计划', '#1890FF']])
    const collapseContextMap = new Map([
      ['DP', { groupType: 'serviceModule', serviceModuleName: '需求计划', title: '需求计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'DP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: {
        serviceModules: new Set(['需求计划']),
        fullyServiceModules: new Map([['需求计划', true]])
      }
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#808080')
  })

  // [PARTIAL-CENTER 2026-08-15] 部分包含对象范围 (既有对象范围内又有范围外元素) → 中性灰.
  it('部分包含对象范围的折叠节点 (hasCenter && !fullyCenter) → 中性灰 #fafafa', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['需求计划', '#1890FF']])
    // DP 服务模块含对象范围内 BO, 也含对象范围外 BO → fully=false
    const collapseContextMap = new Map([
      ['DP', { groupType: 'serviceModule', serviceModuleName: '需求计划', title: '需求计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'DP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: {
        serviceModules: new Set(['需求计划']),
        fullyServiceModules: new Map([['需求计划', false]])
      }
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#fafafa')
  })

  it('部分包含对象范围的折叠子领域节点 (hasCenter && !fullyCenter) → 中性灰 #fafafa', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['供应链计划', '#1890FF']])
    const collapseContextMap = new Map([
      ['SCP', { groupType: 'subDomain', subDomainName: '供应链计划', title: '供应链计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'SCP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: {
        subDomains: new Map([['供应链计划', true]]),
        fullySubDomains: new Map([['供应链计划', false]])
      }
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#fafafa')
  })

  // [PARTIAL-CENTER 2026-08-15] 无 fully 标记 (旧契约) 时, 部分包含不再被误判为纯中心:
  //   旧实现 (仅 hasCenter) 会把部分包含分组染 centerScopeColor, 新实现无 fully 信息时
  //   保守回退中性灰, 而非误染中心色.
  it('旧契约 (无 fully 标记) 的中心分组折叠节点 → 保守回退中性灰而非 centerScopeColor', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['需求计划', '#1890FF']])
    const collapseContextMap = new Map([
      ['DP', { groupType: 'serviceModule', serviceModuleName: '需求计划', title: '需求计划' }]
    ])
    const svg = createCollapseSvg([{ code: 'DP' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'serviceModule', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: {
        serviceModules: new Set(['需求计划'])
        // 无 fullyServiceModules → 视为部分包含, 中性灰 (不误染中心色)
      }
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#fafafa')
  })

  // [FIX 2026-08-09 v3 回归] domains/subDomains 标记的 value 是布尔 (hasCenter), 且所有分组都会写入 map.
  //   旧实现用 .has() 只查 key 存在 → value=false 的非中心领域/子领域也被误判为中心范围 → 折叠节点全染 centerScopeColor.
  it('按 domain 分组: 非中心领域 (markers.domains value=false) 不得被染 centerScopeColor, 应取自身领域色', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([
      ['供应链云', '#1890FF'],
      ['营销云', '#FAAF14']
    ])
    // domains 标记: 所有领域都是 key, 只有 供应链云 hasCenter=true
    const domains = new Map([['供应链云', true], ['制造云', false], ['营销云', false]])
    // [PARTIAL-CENTER 2026-08-15] fully 标记: 供应链云所有子领域都在对象范围 → 完全包含
    const fullyDomains = new Map([['供应链云', true], ['制造云', false], ['营销云', false]])
    const collapseContextMap = new Map([
      ['SCM', { groupType: 'domain', domainName: '供应链云', title: '供应链云' }],
      ['MKT', { groupType: 'domain', domainName: '营销云', title: '营销云' }]
    ])
    const svg = createCollapseSvg([{ code: 'SCM' }, { code: 'MKT' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'domain', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: { domains, fullyDomains }
    })
    // 中心领域 → centerScopeColor
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#808080')
    // 非中心领域 → 自身领域色 (旧 .has() 会错误地返回 centerScopeColor)
    expect(svg.querySelectorAll('g.node.collapseNode')[1].__rect.style.fill).toBe('#FAAF14')
  })

  it('按 subDomain 分组: 非中心子领域 (markers.subDomains value=false) 折叠为领域节点时回退中性灰而非 centerScopeColor', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    // 折叠层级=领域 > 分组层级=子领域 → 非中心领域取不到单一子领域 key → 中性灰 #fafafa
    const colorMap = new Map([['供应链计划', '#1890FF']])
    const subDomains = new Map([['供应链计划', true], ['营销中台', false]])
    const collapseContextMap = new Map([
      ['MKT', { groupType: 'domain', domainName: '营销云', title: '营销云', subDomainName: '' }]
    ])
    const svg = createCollapseSvg([{ code: 'MKT' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'subDomain', colorMap, {
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      centerScopeMarkers: { subDomains }
    })
    // 非中心领域 (营销云, markers.subDomains value=false) → 中性灰, 而非 centerScopeColor
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#fafafa')
  })

  // [CUSTOM-COLOR 2026-08-19] 用户自定义分组的聚合节点保留面板配置色 (customFill),
  //   不被 colorGroupBy 覆盖 (拖入领域/子领域下后仍保持面板色, 用户反馈"变蓝").
  it('用户自定义分组聚合节点: 保留面板色 customFill, 不被 colorGroupBy 覆盖为领域色', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    // colorMap 有供应链云蓝 (#1890FF), 但自定义分组应保持 customFill (#FAAD14 黄)
    const colorMap = new Map([['供应链云', '#1890FF']])
    // 自定义分组: groupType=custom, 无 _elkGroup, 带 customFill=面板色
    const collapseContextMap = new Map([
      ['grp_custom_1', { groupType: 'custom', _elkGroup: '', domainName: '供应链云', title: '分组 1', customFill: '#FAAD14' }]
    ])
    const svg = createCollapseSvg([{ code: 'grp_custom_1' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'domain', colorMap, {
      centerScopeHighlight: false
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#FAAD14')
  })

  it('ELK 系统自动分组 (groupType=custom 且带 _elkGroup) 不被当作自定义分组, 维持 colorGroupBy 覆盖', () => {
    const { updateCollapseNodeColors } = useMermaidColors()
    const colorMap = new Map([['供应链云', '#1890FF']])
    // ELK 系统分组: groupType=custom + _elkGroup='inner', 无 customFill → 走 colorGroupBy 取领域色
    const collapseContextMap = new Map([
      ['SM1_inner', { groupType: 'custom', _elkGroup: 'inner', domainName: '供应链云', title: '无关系', customFill: '' }]
    ])
    const svg = createCollapseSvg([{ code: 'SM1_inner' }])
    updateCollapseNodeColors(svg, collapseContextMap, 'domain', colorMap, {
      centerScopeHighlight: false
    })
    expect(svg.querySelectorAll('g.node.collapseNode')[0].__rect.style.fill).toBe('#1890FF')
  })
})

describe('filterEnabledContainers (Bug 1 回归保护)', () => {
  it('默认 (无 enabled 字段) 全部保留', () => {
    const containers = [
      { name: 'A', nodes: [] },
      { name: 'B', nodes: [] }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
  })

  it('enabled=false 容器被过滤', () => {
    const containers = [
      { name: 'A', enabled: true, nodes: [] },
      { name: 'B', enabled: false, nodes: [] },
      { name: 'C', nodes: [] }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
    expect(result.map(c => c.name)).toEqual(['A', 'C'])
  })

  it('null 容器被过滤', () => {
    const containers = [
      { name: 'A' },
      null,
      undefined,
      { name: 'B' }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
  })

  it('partitionContainersByEnabled 返回 {enabled, disabled}', () => {
    const containers = [
      { name: 'A', enabled: true },
      { name: 'B', enabled: false },
      { name: 'C' }
    ]
    const result = partitionContainersByEnabled(containers)
    expect(result.enabled.map(c => c.name)).toEqual(['A', 'C'])
    expect(result.disabled.map(c => c.name)).toEqual(['B'])
  })
})
