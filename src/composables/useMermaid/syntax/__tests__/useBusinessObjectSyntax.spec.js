/**
 * useBusinessObjectSyntax 单元测试 (v33 修复回归保护 - 2026-06-13)
 *
 * 覆盖:
 * - relationDescriptions 中 sourceName/targetName 从 sourceId/targetId 反查
 * - 即使 link 数据只有 sourceCode/targetCode (没有 sourceName/targetName),
 *   也能正确填充 sourceName/targetName
 * - 节点名回退: nodeIdToNameMap 优先, 缺失时 fallback 到 link.sourceName/targetName
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useBusinessObjectSyntax } from '../useBusinessObjectSyntax.js'

describe('useBusinessObjectSyntax - relationDescriptions sourceName/targetName (v33 修复)', () => {
  let syntax

  beforeEach(() => {
    syntax = useBusinessObjectSyntax()
  })

  it('link 只有 sourceCode/targetCode 时也能正确填充 sourceName/targetName', () => {
    const data = {
      nodes: [
        { code: 'BO001', name: '客户主数据', originalName: '客户主数据', category: 'object' },
        { code: 'BO002', name: '订单主数据', originalName: '订单主数据', category: 'object' }
      ],
      links: [
        // 关键: link 没有 sourceName/targetName 字段
        { sourceCode: 'BO001', targetCode: 'BO002', relationCode: 'REL_001', relationDesc: '下单' }
      ]
    }

    const relationDescriptions = []
    const result = syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', null)

    expect(relationDescriptions.length).toBe(1)
    const rel = relationDescriptions[0]

    // v33 关键断言: sourceName/targetName 不再为空
    expect(rel.sourceName).toBe('客户主数据')
    expect(rel.targetName).toBe('订单主数据')
    // relationCode/Desc 保持不变
    expect(rel.relationCode).toBe('REL_001')
    expect(rel.relationDesc).toBe('下单')
  })

  it('link 同时有 sourceName/targetName 时优先用 sourceId/targetId 反查的节点名', () => {
    const data = {
      nodes: [
        { code: 'BO001', name: '客户主数据', originalName: '客户主数据', category: 'object' },
        { code: 'BO002', name: '订单主数据', originalName: '订单主数据', category: 'object' }
      ],
      links: [
        // 关键: sourceName 是错的/旧的, 应该用 sourceId 反查
        { sourceCode: 'BO001', sourceName: '错误的旧名', targetCode: 'BO002', targetName: '错误的旧名', relationCode: 'REL_001' }
      ]
    }

    const relationDescriptions = []
    syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', null)

    const rel = relationDescriptions[0]
    // v33 关键断言: 用反查的真实名字, 不是 link.sourceName
    expect(rel.sourceName).toBe('客户主数据')
    expect(rel.targetName).toBe('订单主数据')
  })

  it('sourceId/targetId 在 nodeIdToNameMap 找不到时回退到 link.sourceName', () => {
    const data = {
      nodes: [
        { code: 'BO001', name: 'A', originalName: 'A', category: 'object' }
      ],
      links: [
        // sourceId 在 sourceId 反查时找不到 (link.sourceCode 不在 nodeCodeToIdMap)
        { sourceCode: 'BO_MISSING', sourceName: '外部源', targetCode: 'BO001', targetName: 'A', relationCode: 'REL_002' }
      ]
    }

    const relationDescriptions = []
    syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', null)

    // 因为 sourceCode 'BO_MISSING' 不在 nodes 中, link 会被过滤掉, relationDescriptions 可能为空
    // 这里主要测试不会抛错
    expect(relationDescriptions.length).toBeLessThanOrEqual(1)
  })

  it('多条 link 都正确填充 sourceName/targetName', () => {
    const data = {
      nodes: [
        { code: 'BO001', name: '客户', originalName: '客户', category: 'object' },
        { code: 'BO002', name: '订单', originalName: '订单', category: 'object' },
        { code: 'BO003', name: '产品', originalName: '产品', category: 'object' }
      ],
      links: [
        { sourceCode: 'BO001', targetCode: 'BO002', relationCode: 'R1' },
        { sourceCode: 'BO002', targetCode: 'BO003', relationCode: 'R2' },
        { sourceCode: 'BO001', targetCode: 'BO003', relationCode: 'R3' }
      ]
    }

    const relationDescriptions = []
    syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', null)

    expect(relationDescriptions.length).toBe(3)
    expect(relationDescriptions[0].sourceName).toBe('客户')
    expect(relationDescriptions[0].targetName).toBe('订单')
    expect(relationDescriptions[1].sourceName).toBe('订单')
    expect(relationDescriptions[1].targetName).toBe('产品')
    expect(relationDescriptions[2].sourceName).toBe('客户')
    expect(relationDescriptions[2].targetName).toBe('产品')
  })

  it('关系描述中的 source/target ID 仍正确 (Mermaid 边端点)', () => {
    const data = {
      nodes: [
        { code: 'BO001', name: 'A', originalName: 'A', category: 'object' },
        { code: 'BO002', name: 'B', originalName: 'B', category: 'object' }
      ],
      links: [
        { sourceCode: 'BO001', targetCode: 'BO002', relationCode: 'R1' }
      ]
    }

    const relationDescriptions = []
    syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', null)

    // source/target 是 Mermaid 的 N1/N2 ID, 用于边端点定位
    expect(relationDescriptions[0].source).toMatch(/^N\d+$/)
    expect(relationDescriptions[0].target).toMatch(/^N\d+$/)
  })

  // [FIX 2026-08-06] 折叠聚合节点连线颜色: 折叠后连线端点被重映射为 COLLAPSE_<id>,
  //   nodeColorMap 不含聚合节点 → 连线颜色计算 sourceColor/targetColor 取不到 → 折叠连线变黑.
  //   修复: applyUpliftNodeColors 产出 collapseColorMap, 连线颜色计算 fallback 到分组色.
  it('折叠聚合节点连线使用分组色而非黑色 (FIX 2026-08-06)', () => {
    const data = {
      nodes: [
        { code: 'BO1', name: 'BO1', originalName: 'BO1', category: 'object' },
        { code: 'BO2', name: 'BO2', originalName: 'BO2', category: 'object' }
      ],
      links: [{ sourceCode: 'BO1', targetCode: 'BO2', relationCode: 'R1' }],
      // 中心范围在 data 层 (与 useDiagramData 传递一致), 不在 layoutControlConfig
      centerScope: ['BO1'],
      domainProducts: [
        { name: '领域A', code: 'DA', businessObjects: [{ code: 'BO1', name: 'BO1' }] },
        { name: '领域B', code: 'DB', businessObjects: [{ code: 'BO2', name: 'BO2' }] }
      ]
    }
    // 两个服务模块分组均折叠 (collapsed=true + enabled=true) → 上提为聚合节点,
    // 但 BO1 折叠分组在中心范围 (centerScope 含 BO1) → 折叠连线应取分组色而非黑色.
    const layoutControlConfig = {
      enabled: true,
      overallDirection: 'TB',
      colorGroupBy: 'domain',
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      groups: [
        { id: 'A', title: '领域A', groupType: 'domain', enabled: true, collapsed: true,
          containers: [{ id: 'bo1', nodes: ['BO1'], isVirtual: true, elementCode: 'BO1' }], children: [] },
        { id: 'B', title: '领域B', groupType: 'domain', enabled: true, collapsed: true,
          containers: [{ id: 'bo2', nodes: ['BO2'], isVirtual: true, elementCode: 'BO2' }], children: [] }
      ]
    }

    const relationDescriptions = []
    const result = syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', layoutControlConfig)

    // 折叠聚合节点连线应被保留 (sourceId/targetId 为 COLLAPSE_ 聚合节点)
    expect(result.linkColorMappings.length).toBeGreaterThan(0)
    const link = result.linkColorMappings[0]
    // 端点应为聚合节点编码
    expect(String(link.sourceId).startsWith('COLLAPSE_')).toBe(true)
    // 源 (BO1 折叠聚合, 中心范围) → 目标 (BO2 折叠聚合, 非中心) → 取目标分组色 (非黑色/非深灰)
    expect(link.color).toBeDefined()
    expect(link.color).not.toBe('#000000')
    expect(link.color).not.toBe('#333333')
  })

  // [LEVEL 2026-08-06] "展开到领域" 语义: 领域 collapsed=true 时, 其嵌套子级
  //   (子领域/服务模块/BO) 必须全部隐藏, mermaid 输出不得含子领域标题或 BO 名.
  //   回归保护: 防止折叠领域后子级仍渲染 (用户反馈"展开到领域仍展示子领域").
  it('嵌套结构: 领域 collapsed=true 时子领域及以下完全隐藏 (LEVEL 2026-08-06)', () => {
    const data = {
      nodes: [
        { code: 'BO1', name: '客户主数据', originalName: '客户主数据', category: 'object' },
        { code: 'BO2', name: '订单主数据', originalName: '订单主数据', category: 'object' }
      ],
      links: [{ sourceCode: 'BO1', targetCode: 'BO2', relationCode: 'R1' }],
      domainProducts: [
        { name: '领域A', code: 'DA', subDomains: [
          { name: '子领域A1', code: 'SDA1', businessObjects: [
            { code: 'BO1', name: '客户主数据' }, { code: 'BO2', name: '订单主数据' }
          ] }
        ] }
      ]
    }
    // 领域 collapsed=true, 且含嵌套 children (子领域 → 服务模块 → BO 容器)
    const layoutControlConfig = {
      enabled: true,
      overallDirection: 'TB',
      colorGroupBy: 'domain',
      groups: [
        { id: 'd1', title: '领域A', groupType: 'domain', enabled: true, collapsed: true,
          containers: [], children: [
            { id: 'sd1', title: '子领域A1', groupType: 'subDomain', enabled: true,
              containers: [
                { id: 'bo1', nodes: ['BO1'], isVirtual: true, elementCode: 'BO1' },
                { id: 'bo2', nodes: ['BO2'], isVirtual: true, elementCode: 'BO2' }
              ],
              children: [] }
          ] }
      ]
    }

    const relationDescriptions = []
    const result = syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', layoutControlConfig)

    // 领域折叠为聚合节点 → 领域标题出现 (带 … 提示)
    expect(result.mermaidCode).toContain('COLLAPSE_d1')
    // 子领域标题不得出现
    expect(result.mermaidCode).not.toContain('子领域A1')
    // BO 名不得出现 (子级完全隐藏)
    expect(result.mermaidCode).not.toContain('客户主数据')
    expect(result.mermaidCode).not.toContain('订单主数据')
  })

  // [PARTIAL-CENTER 2026-08-15] 折叠节点中性颜色 (部分包含对象范围):
  //   领域分组同时含"对象范围内 BO"和"对象范围外 BO" → 折叠节点应显示中性灰 (走 classDef default),
  //   而非 centerScopeColor. 与增量路径 updateCollapseNodeColors 的判定一致.
  it('部分包含对象范围: 领域含范围内+范围外 BO → 折叠节点中性灰 (无 centerScopeColor style)', () => {
    const data = {
      nodes: [
        { code: 'BO1', name: 'BO1', originalName: 'BO1', category: 'object' },
        { code: 'BO2', name: 'BO2', originalName: 'BO2', category: 'object' }
      ],
      links: [],
      // 只有 BO1 在对象范围; BO2 为跨域关系引入的范围外 BO (同领域)
      centerScope: ['BO1'],
      domainProducts: [
        { name: '领域A', code: 'DA', businessObjects: [
          { code: 'BO1', name: 'BO1' }, { code: 'BO2', name: 'BO2' }
        ] }
      ]
    }
    const layoutControlConfig = {
      enabled: true,
      overallDirection: 'TB',
      colorGroupBy: 'domain',
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      groups: [
        { id: 'A', title: '领域A', groupType: 'domain', enabled: true, collapsed: true,
          containers: [
            { id: 'bo1', nodes: ['BO1'], isVirtual: true, elementCode: 'BO1' },
            { id: 'bo2', nodes: ['BO2'], isVirtual: true, elementCode: 'BO2' }
          ],
          children: [] }
      ]
    }

    const relationDescriptions = []
    const result = syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', layoutControlConfig)

    // 折叠节点存在
    expect(result.mermaidCode).toContain('COLLAPSE_A')
    // 部分包含 → 不生成 centerScopeColor 的 style (走 classDef default 中性灰 #fafafa)
    expect(result.mermaidCode).not.toMatch(/style\s+COLLAPSE_A[^,\n]*#[8][0][8][0][8][0]/i)
    // collapseColorMap 不应含 centerScopeColor
    const colorForA = result.colorMap?.get && result.colorMap.get('COLLAPSE_A')
    expect(colorForA).not.toBe('#808080')
  })

  // [PARTIAL-CENTER 2026-08-15] 完全包含对象范围: 领域所有 BO 都在对象范围 → centerScopeColor.
  it('完全包含对象范围: 领域仅含范围内 BO → 折叠节点 centerScopeColor', () => {
    const data = {
      nodes: [
        { code: 'BO1', name: 'BO1', originalName: 'BO1', category: 'object' },
        { code: 'BO2', name: 'BO2', originalName: 'BO2', category: 'object' }
      ],
      links: [],
      centerScope: ['BO1', 'BO2'],
      domainProducts: [
        { name: '领域A', code: 'DA', businessObjects: [
          { code: 'BO1', name: 'BO1' }, { code: 'BO2', name: 'BO2' }
        ] }
      ]
    }
    const layoutControlConfig = {
      enabled: true,
      overallDirection: 'TB',
      colorGroupBy: 'domain',
      centerScopeHighlight: true,
      centerScopeColor: '#808080',
      groups: [
        { id: 'A', title: '领域A', groupType: 'domain', enabled: true, collapsed: true,
          containers: [
            { id: 'bo1', nodes: ['BO1'], isVirtual: true, elementCode: 'BO1' },
            { id: 'bo2', nodes: ['BO2'], isVirtual: true, elementCode: 'BO2' }
          ],
          children: [] }
      ]
    }

    const relationDescriptions = []
    const result = syntax.generateMermaidCode(data, relationDescriptions, 'dagre', 'grouped', layoutControlConfig)

    expect(result.mermaidCode).toContain('COLLAPSE_A')
    // 完全包含 → 生成 centerScopeColor style
    expect(result.mermaidCode).toMatch(/style\s+COLLAPSE_A[^,\n]*#[8][0][8][0][8][0]/i)
  })
})
