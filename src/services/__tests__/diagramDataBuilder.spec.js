/**
 * @file diagramDataBuilder.spec.js
 * @description [v34 双向支持] diagramDataBuilder 数据透传测试
 *
 * 覆盖关键数据流 bug:
 * - 之前 buildLinks() 漏掉透传 relationType + relationDirection
 * - 导致下游 tooltip / 箭头生成拿不到方向信息
 * - 修复后: buildLinks 输出包含 relationType + relationDirection
 */
import { describe, it, expect } from 'vitest'
import { buildLinks } from '../diagramDataBuilder.js'

describe('diagramDataBuilder - buildLinks (v34 双向支持数据流)', () => {
  it('透传 relationType (BusinessRelationType code)', () => {
    const links = buildLinks([{
      sourceName: 'A',
      targetName: 'B',
      sourceCode: 'A',
      targetCode: 'B',
      relationCode: 'R1',
      relationDesc: 'desc',
      relationType: 'GENERATES',
      relationDirection: '推'
    }])
    expect(links[0].relationType).toBe('GENERATES')
  })

  it('透传 relationDirection (推/拉/双向)', () => {
    const links = buildLinks([{
      sourceName: 'A',
      targetName: 'B',
      sourceCode: 'A',
      targetCode: 'B',
      relationCode: 'R1',
      relationDesc: 'desc',
      relationType: 'DEPENDS_ON',
      relationDirection: '双向'
    }])
    expect(links[0].relationDirection).toBe('双向')
  })

  it('同时透传 relationType + relationDirection', () => {
    const links = buildLinks([{
      sourceName: '源',
      targetName: '目标',
      sourceCode: 'SRC',
      targetCode: 'TGT',
      relationCode: 'PUM01-PUM02-01',
      relationDesc: '业务关系',
      relationType: 'DEPENDS_ON',
      relationDirection: '双向'
    }])
    expect(links[0]).toMatchObject({
      relationType: 'DEPENDS_ON',
      relationDirection: '双向',
      relationCode: 'PUM01-PUM02-01',
      sourceCode: 'SRC',
      targetCode: 'TGT',
      sourceName: '源',
      targetName: '目标'
    })
  })

  it('缺 relationType 字段时用空字符串 (向后兼容)', () => {
    const links = buildLinks([{
      sourceName: 'A',
      targetName: 'B',
      sourceCode: 'A',
      targetCode: 'B',
      relationCode: 'R1',
      relationDesc: 'desc'
      // 注意: 没有 relationType / relationDirection
    }])
    expect(links[0].relationType).toBe('')
    expect(links[0].relationDirection).toBe(null)
  })

  it('多条关系: 每条都透传自己的 direction', () => {
    const links = buildLinks([
      { sourceName: 'A', targetName: 'B', relationCode: 'R1', relationType: 'T1', relationDirection: '推' },
      { sourceName: 'B', targetName: 'A', relationCode: 'R2', relationType: 'T2', relationDirection: '拉' },
      { sourceName: 'A', targetName: 'B', relationCode: 'R3', relationType: 'T3', relationDirection: '双向' }
    ])
    expect(links).toHaveLength(3)
    expect(links[0].relationDirection).toBe('推')
    expect(links[1].relationDirection).toBe('拉')
    expect(links[2].relationDirection).toBe('双向')
  })

  it('relationDirection 为 null 时 (数据源没填) - 输出 null', () => {
    const links = buildLinks([{
      sourceName: 'A',
      targetName: 'B',
      relationCode: 'R1',
      relationDirection: null
    }])
    expect(links[0].relationDirection).toBe(null)
  })
})
