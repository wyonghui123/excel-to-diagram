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
import { buildLinks, buildDiagramData } from '../diagramDataBuilder.js'

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

// [Task 10 2026-08-02] BO 图统一管道分支 (spec 4.2): projectTree(businessObject) 投影形状
describe('diagramDataBuilder - 统一管道分支 (chartType=businessObject)', () => {
  const domainProducts = [{
    name: '供应链', code: 'SC',
    modules: [{
      name: '子域A', code: 'SD1',
      submodules: [{
        name: '采购服务', code: 'SM1',
        businessObjects: [{ code: 'BO1', name: '采购订单' }, { code: 'BO2', name: '供应商' }]
      }]
    }]
  }]
  const businessObjects = [
    { code: 'BO1', name: '采购订单', serviceModule: 'SM1', serviceModuleName: '采购服务', domain: '供应链', subDomain: '子域A' },
    { code: 'BO2', name: '供应商', serviceModule: 'SM1', serviceModuleName: '采购服务', domain: '供应链', subDomain: '子域A' }
  ]
  const relationships = [{
    sourceCode: 'BO1', targetCode: 'BO2',
    code: 'PUR-BO1-BO2-01', relationCode: 'DEPENDS_ON', relationDesc: '依赖',
    relationType: 'DEPENDS_ON', relationDirection: '双向',
    annotationContents: ['备注A'], annotationCategories: ['info']
  }]

  const data = buildDiagramData({
    businessObjects, relationships, domainProducts, serviceModules: [],
    preview: { domainProducts, relationships },
    chartType: 'businessObject',
    centerScope: ['BO1'], centerScopeHighlight: true
  })

  it('节点来自投影: id=code + BO 语法层契约字段 (category/name/serviceModule)', () => {
    expect(data.nodes).toHaveLength(2)
    expect(data.nodes[0]).toMatchObject({
      id: 'BO1', code: 'BO1', category: 'object',
      name: '采购订单', originalName: '采购订单',
      serviceModule: 'SM1', serviceModuleName: '采购服务',
      domain: '供应链', subDomain: '子域A',
      isCenter: true
    })
    expect(data.nodes[1].id).toBe('BO2')
  })

  it('容器来自投影: D→SD→SM 嵌套树, SM 叶容器 nodeIds=BO codes', () => {
    expect(data.containers).toHaveLength(1)
    const d = data.containers[0]
    expect(d.layer).toBe('DOMAIN')
    expect(d.children[0].layer).toBe('SUB_DOMAIN')
    const sm = d.children[0].children[0]
    expect(sm.layer).toBe('SERVICE_MODULE')
    expect(sm.nodeIds).toEqual(['BO1', 'BO2'])
  })

  it('links 重映射为 BO code 级 + 关系元数据透传 (label/双向/备注)', () => {
    expect(data.links).toHaveLength(1)
    expect(data.links[0]).toMatchObject({
      source: 'BO1', target: 'BO2',
      sourceCode: 'BO1', targetCode: 'BO2',
      sourceName: '采购订单', targetName: '供应商',
      code: 'PUR-BO1-BO2-01', relationCode: 'DEPENDS_ON',
      relationType: 'DEPENDS_ON', relationDirection: '双向',
      annotationContents: ['备注A'], annotationCategories: ['info']
    })
  })

  it('layoutControlConfig 由同一容器树派生 (deriveLayoutGroups), groupType 标记管道产物', () => {
    const groups = data.layoutControlConfig.groups
    expect(data.layoutControlConfig.enabled).toBe(true)
    expect(groups[0].groupType).toBe('domain')
    expect(groups[0].children[0].groupType).toBe('subDomain')
    const smGroup = groups[0].children[0].children[0]
    expect(smGroup.groupType).toBe('serviceModule')
    // SM 叶容器 → directNodes (BO codes), 非 containers (避免 SM 终端包一层 subgraph 重复渲染)
    expect(smGroup.directNodes).toEqual(['BO1', 'BO2'])
  })

  it('不传 preview 时保持旧路径 (节点 id=name)', () => {
    const legacy = buildDiagramData({ businessObjects, relationships, domainProducts })
    expect(legacy.nodes[0].id).toBe('采购订单')
    expect(legacy.links[0].sourceCode).toBe('BO1')
  })
})
