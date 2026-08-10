/**
 * linkRemapper.fuseLinks 单测 (2026-08-09)
 *
 * 覆盖"一个连线背后对应多个关系"的融合语义:
 * - ①方向相反融合为双向 (A->B + B->A)
 * - ②同源目标但关系编码不同 (A-B-01 + A-B-02)
 * - 融合后代表连线需携带 childRelations 全部关系元数据 (供 BO 图 tooltip 列示)
 * - relationCode 为空时回退到 code/label, 保证子关系"关系编码"行非空
 */
import { describe, it, expect } from 'vitest'
import { fuseLinks } from '../linkRemapper'

function mkLink({ source = 'A', target = 'B', code, relationCode = '', sourceName = '源', targetName = '目标', relationType = 'GENERATES', relationDirection = 'PUSH', relationDesc = '说明' }) {
  return { source, target, sourceCode: source, targetCode: target, code: code || `${source}-${target}`, relationCode, sourceName, targetName, relationType, relationDirection, relationDesc, label: code || `${source}-${target}` }
}

describe('fuseLinks - 多关系融合为单连线', () => {
  it('同源目标不同关系编码 (A-B-01 + A-B-02) → 保留一条连线 + childRelations 两条', () => {
    const links = [
      mkLink({ code: 'A-B-01', relationCode: 'A-B-01', relationDesc: '关系一', relationType: 'GENERATES', relationDirection: 'PUSH' }),
      mkLink({ code: 'A-B-02', relationCode: 'A-B-02', relationDesc: '关系二', relationType: 'COMPOSES', relationDirection: 'PULL' })
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(Array.isArray(fused[0].childRelations)).toBe(true)
    expect(fused[0].childRelations.length).toBe(2)
    // 子关系逐条携带独立元数据
    expect(fused[0].childRelations[0].relationCode).toBe('A-B-01')
    expect(fused[0].childRelations[0].relationDesc).toBe('关系一')
    expect(fused[0].childRelations[0].relationType).toBe('GENERATES')
    expect(fused[0].childRelations[0].relationDirection).toBe('PUSH')
    expect(fused[0].childRelations[1].relationCode).toBe('A-B-02')
    expect(fused[0].childRelations[1].relationDesc).toBe('关系二')
  })

  it('方向相反 (A->B + B->A) → 融合为 BIDIRECTIONAL + childRelations 两条', () => {
    const links = [
      mkLink({ source: 'A', target: 'B', relationDirection: 'PUSH', relationDesc: 'A到B' }),
      mkLink({ source: 'B', target: 'A', relationDirection: 'PULL', relationDesc: 'B到A' })
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].relationDirection).toBe('BIDIRECTIONAL')
    expect(fused[0].childRelations.length).toBe(2)
    // 子关系各自方向不被覆盖 (保留原始 PUSH/PULL)
    expect(fused[0].childRelations.map(c => c.relationDirection).sort()).toEqual(['PULL', 'PUSH'])
  })

  it('relationCode 为空时子关系回退到 code/label, 保证"关系编码"行非空 (arch data 流程)', () => {
    const links = [
      mkLink({ code: 'PLA001-PLD00201', relationCode: '', relationDesc: '从计划范围生成需求计划薄' }),
      mkLink({ code: 'PLA001-PLD00201', relationCode: '', relationDesc: '另一条关系' })
    ]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].childRelations.length).toBe(2)
    fused[0].childRelations.forEach(c => {
      expect(c.relationCode).toBe('PLA001-PLD00201') // 回退到 code
    })
  })

  it('单条关系 → 不设置 childRelations (向后兼容老逻辑)', () => {
    const links = [mkLink({ code: 'A-B' })]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].childRelations).toBeUndefined()
  })

  it('单条已标记双向 → BIDIRECTIONAL 但不设置 childRelations', () => {
    const links = [mkLink({ code: 'A-B', relationDirection: 'BIDIRECTIONAL' })]
    const fused = fuseLinks(links)
    expect(fused.length).toBe(1)
    expect(fused[0].relationDirection).toBe('BIDIRECTIONAL')
    expect(fused[0].childRelations).toBeUndefined()
  })
})
