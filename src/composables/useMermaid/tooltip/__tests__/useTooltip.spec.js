/**
 * @file useTooltip.spec.js
 * @description [v34 双向支持] useTooltip 单元测试
 *
 * 覆盖 formatTooltipText 增强版:
 * - 关系类型 (relationType) 展示 + BusinessRelationType 枚举解析
 * - 关系方向 (relationDirection) 展示 (推/拉/双向)
 * - 缺字段容错 (无 relationType / relationDirection 不展示)
 * - 枚举缓存缺失时的 fallback
 * - 关系类型 + 方向 同时存在时的排版
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useTooltip } from '../useTooltip.js'

describe('useTooltip - formatTooltipText (v34 双向支持)', () => {
  let api

  beforeEach(() => {
    api = useTooltip()
  })

  afterEach(() => {
    // 清理 window 上的 mock
    if (typeof window !== 'undefined' && window.__relationTypeEnumMap) {
      delete window.__relationTypeEnumMap
    }
  })

  it('formatTooltipText 是函数, 已导出', () => {
    expect(typeof api.formatTooltipText).toBe('function')
  })

  it('relation 为 null 时返回 "无关系说明"', () => {
    expect(api.formatTooltipText(null)).toBe('无关系说明')
  })

  it('relation 为 undefined 时返回 "无关系说明"', () => {
    expect(api.formatTooltipText(undefined)).toBe('无关系说明')
  })

  it('基础展示: 关系码 + 源→目标 + 描述', () => {
    const text = api.formatTooltipText({
      relationCode: 'PUM01-PUM02-01',
      sourceName: '源节点',
      targetName: '目标节点',
      relationDesc: '测试关系'
    })
    expect(text).toContain('PUM01-PUM02-01')
    expect(text).toContain('源节点 → 目标节点')
    expect(text).toContain('测试关系')
  })

  it('无 relationDesc 时显示 "无关系说明"', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B'
    })
    expect(text).toContain('无关系说明')
  })

  it('🆕 关系方向 推 - 添加 "方向: 推" 行', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationDirection: '推'
    })
    expect(text).toContain('方向: 推')
  })

  it('🆕 关系方向 拉 - 添加 "方向: 拉" 行', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationDirection: '拉'
    })
    expect(text).toContain('方向: 拉')
  })

  it('🆕 关系方向 双向 - 添加 "方向: 双向" 行', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationDirection: '双向'
    })
    expect(text).toContain('方向: 双向')
  })

  it('🆕 关系类型 code 无枚举时 - 显示原始 code', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: 'GENERATES'
    })
    expect(text).toContain('类型: GENERATES')
    // 没有 label 时不应该有括号
    expect(text).not.toContain('类型: GENERATES (')
  })

  it('🆕 关系类型 code 有枚举 - 显示 "中文名 (CODE)" 格式', () => {
    window.__relationTypeEnumMap = {
      GENERATES: { code: 'GENERATES', label: '生成' }
    }
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: 'GENERATES'
    })
    expect(text).toContain('类型: 生成 (GENERATES)')
  })

  it('🆕 关系类型枚举缓存不包含该 code - fallback 到原始 code', () => {
    window.__relationTypeEnumMap = {
      // 注意: 故意不含 DEPENDS_ON
      OTHER: { code: 'OTHER', label: '其他' }
    }
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: 'DEPENDS_ON'
    })
    expect(text).toContain('类型: DEPENDS_ON')
  })

  it('🆕 关系类型 + 方向 同时存在 - 排版正确', () => {
    window.__relationTypeEnumMap = {
      DEPENDS_ON: { code: 'DEPENDS_ON', label: '依赖' }
    }
    const text = api.formatTooltipText({
      relationCode: 'PUM01-PUM02-01',
      sourceName: '源',
      targetName: '目标',
      relationDesc: '业务关系',
      relationType: 'DEPENDS_ON',
      relationDirection: '双向'
    })
    expect(text).toContain('PUM01-PUM02-01')
    expect(text).toContain('源 → 目标')
    expect(text).toContain('类型: 依赖 (DEPENDS_ON)')
    expect(text).toContain('方向: 双向')
    expect(text).toContain('业务关系')
  })

  it('🆕 关系类型 + 方向 + 备注 - 完整排版', () => {
    window.__relationTypeEnumMap = {
      GENERATES: { code: 'GENERATES', label: '生成' }
    }
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: 'GENERATES',
      relationDirection: '推',
      annotationContent: '业务注释'
    })
    expect(text).toContain('R1')
    expect(text).toContain('A → B')
    expect(text).toContain('类型: 生成 (GENERATES)')
    expect(text).toContain('方向: 推')
    expect(text).toContain('desc')
    expect(text).toContain('备注: 业务注释')
  })

  it('无 relationType + 无 relationDirection - 不展示类型/方向行 (向后兼容)', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc'
    })
    expect(text).not.toContain('类型:')
    expect(text).not.toContain('方向:')
  })

  it('空 relationType / relationDirection (空字符串) - 不展示', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: '',
      relationDirection: ''
    })
    expect(text).not.toContain('类型:')
    expect(text).not.toContain('方向:')
  })

  it('枚举缓存存在但 value 没有 label - fallback 到 code', () => {
    window.__relationTypeEnumMap = {
      GENERATES: { code: 'GENERATES' }  // 注意: 没有 label 字段
    }
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      relationType: 'GENERATES'
    })
    expect(text).toContain('类型: GENERATES')
  })

  it('枚举缓存存在但 value 是 null - 不抛错, fallback 到 code', () => {
    window.__relationTypeEnumMap = {
      GENERATES: null
    }
    expect(() => {
      const text = api.formatTooltipText({
        relationCode: 'R1',
        sourceName: 'A',
        targetName: 'B',
        relationDesc: 'desc',
        relationType: 'GENERATES'
      })
      expect(text).toContain('类型: GENERATES')
    }).not.toThrow()
  })

  it('行序正确: code → source→target → 类型 → 方向 → 描述 → 备注', () => {
    window.__relationTypeEnumMap = {
      GENERATES: { code: 'GENERATES', label: '生成' }
    }
    const text = api.formatTooltipText({
      relationCode: 'PUM01-PUM02-01',
      sourceName: '源',
      targetName: '目标',
      relationDesc: '业务描述',
      relationType: 'GENERATES',
      relationDirection: '双向',
      annotationContent: '业务注释'
    })
    const lines = text.split('\n')
    // 找到各行的索引
    const codeIdx = lines.findIndex(l => l.includes('PUM01-PUM02-01'))
    const arrowIdx = lines.findIndex(l => l.includes('源 → 目标'))
    const typeIdx = lines.findIndex(l => l.includes('类型:'))
    const dirIdx = lines.findIndex(l => l.includes('方向:'))
    const descIdx = lines.findIndex(l => l.includes('业务描述'))
    const noteIdx = lines.findIndex(l => l.includes('备注:'))

    // 行序严格保证
    expect(codeIdx).toBeLessThan(arrowIdx)
    expect(arrowIdx).toBeLessThan(typeIdx)
    expect(typeIdx).toBeLessThan(dirIdx)
    expect(dirIdx).toBeLessThan(descIdx)
    expect(descIdx).toBeLessThan(noteIdx)
  })
})

describe('useTooltip - formatTooltipText 聚合级关系数量统计 (2026-08-09)', () => {
  let api
  beforeEach(() => {
    api = useTooltip()
  })

  it('任一端为折叠容器 (level<=2) → 只展示关系数量统计, 不含方向/类型等关系级属性', () => {
    const text = api.formatTooltipText({
      relationCode: 'PLAM-SNPSP',
      sourceName: '供应链计划',
      targetName: '销售计划',
      sourceLevel: 1,
      targetLevel: 1,
      childRelations: [
        { relationCode: 'A', sourceName: 'a', targetName: 'b', relationDirection: 'PUSH', relationType: 'GENERATES' },
        { relationCode: 'B', sourceName: 'b', targetName: 'a', relationDirection: 'PULL', relationType: 'GENERATES' },
        { relationCode: 'C', sourceName: 'c', targetName: 'd', relationDirection: 'PUSH', relationType: 'COMPOSES' }
      ]
    })
    // 总条数
    expect(text).toContain('共 3 条')
    // 不逐条列示 (不出现 [1]/[2]/[3] 子关系标记)
    expect(text).not.toContain('[1]')
    expect(text).not.toContain('[2]')
    // 聚合级不展示方向/类型 (只在 BO 级列示中展示)
    expect(text).not.toContain('方向:')
    expect(text).not.toContain('类型:')
  })

  it('聚合级 + childRelations 为空 (仅 1 条底层关系) → 总数显示 1', () => {
    const text = api.formatTooltipText({
      relationCode: 'PLAM-SNPSP',
      sourceName: '供应链计划',
      targetName: '销售计划',
      sourceLevel: 1,
      targetLevel: 2
    })
    expect(text).toContain('共 1 条')
  })

  it('两端均为 BO (level=3) → 不受聚合统计影响, 走 childRelations 逐条列表', () => {
    const text = api.formatTooltipText({
      relationCode: 'PLA001-PLD00201',
      sourceName: '计划范围',
      targetName: '需求计划薄',
      sourceLevel: 3,
      targetLevel: 3,
      childRelations: [
        { relationCode: 'A', sourceName: '计划范围', targetName: '需求计划薄', relationDirection: 'PUSH' },
        { relationCode: 'B', sourceName: '需求计划薄', targetName: '计划范围', relationDirection: 'PULL' }
      ]
    })
    expect(text).toContain('共 2 条子关系:')
    expect(text).toContain('[1]')
    expect(text).toContain('[2]')
    expect(text).not.toContain('关系数量:')
  })
})

describe('useTooltip - formatTooltipText childRelations 多关系列示 (2026-08-09)', () => {
  let api
  beforeEach(() => {
    api = useTooltip()
  })

  it('childRelations 非空 → 展示父关系概览 + 逐条子关系 (编码/名称/类型/方向/描述)', () => {
    const text = api.formatTooltipText({
      relationCode: 'PLA001-PLD00201',
      sourceName: '计划范围',
      targetName: '需求计划薄',
      childRelations: [
        { relationCode: 'PLA001-PLD00201', sourceName: '计划范围', targetName: '需求计划薄', relationType: 'GENERATES', relationDirection: 'PUSH', relationDesc: '从计划范围生成需求计划薄' },
        { relationCode: 'PLA001-PLD00201', sourceName: '需求计划薄', targetName: '计划范围', relationType: 'GENERATES', relationDirection: 'PULL', relationDesc: '反向关联' }
      ]
    })
    expect(text).toContain('共 2 条子关系:')
    expect(text).toContain('[1]')
    expect(text).toContain('[2]')
    // 父概览
    expect(text).toContain('计划范围 → 需求计划薄')
    // 子关系逐条含编码/类型/方向/描述
    // 注: 单测环境 relation_direction enum 未加载 → 方向/类型显示原始 code (与真实渲染的"双向 (BIDIRECTIONAL)"映射由 enum 提供)
    expect(text).toContain('方向: PUSH')
    expect(text).toContain('方向: PULL')
    expect(text).toContain('类型: GENERATES')
    expect(text).toContain('从计划范围生成需求计划薄')
    expect(text).toContain('反向关联')
  })

  it('childRelations 为空数组 → 走单关系老逻辑 (向后兼容)', () => {
    const text = api.formatTooltipText({
      relationCode: 'R1',
      sourceName: 'A',
      targetName: 'B',
      relationDesc: 'desc',
      childRelations: []
    })
    expect(text).not.toContain('子关系')
    expect(text).toContain('A → B')
  })
})
