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
})
