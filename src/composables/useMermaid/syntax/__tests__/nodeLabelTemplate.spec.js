import { describe, it, expect } from 'vitest'
import {
  extractOwnGroupName,
  getContainerMarkers,
  collapseFormatMarker,
  businessObjectLabel
} from '../nodeLabelTemplate.js'

describe('nodeLabelTemplate.extractOwnGroupName', () => {
  it('去除非空输入的空格', () => {
    expect(extractOwnGroupName(' 销售 ')).toBe('销售')
  })

  it('去掉末尾全角括号组', () => {
    expect(extractOwnGroupName('销售（供应链云）')).toBe('销售')
  })

  it('去掉末尾半角括号组', () => {
    expect(extractOwnGroupName('销售(供应链云)')).toBe('销售')
  })

  it('无括号时保持原样', () => {
    expect(extractOwnGroupName('供应链计划')).toBe('供应链计划')
  })

  it('空/undefined 原样返回', () => {
    expect(extractOwnGroupName('')).toBe('')
    expect(extractOwnGroupName(null)).toBe(null)
    expect(extractOwnGroupName(undefined)).toBe(undefined)
  })
})

describe('nodeLabelTemplate.getContainerMarkers', () => {
  it('domain → 尖括号', () => {
    expect(getContainerMarkers('domain')).toEqual(['<', '>'])
    expect(getContainerMarkers('DOMAIN')).toEqual(['<', '>'])
  })

  it('subdomain → 花括号', () => {
    expect(getContainerMarkers('subdomain')).toEqual(['{', '}'])
    expect(getContainerMarkers('SUB_DOMAIN')).toEqual(['{', '}'])
  })

  it('servicemodule → 方括号', () => {
    expect(getContainerMarkers('servicemodule')).toEqual(['[', ']'])
    expect(getContainerMarkers('SERVICE_MODULE')).toEqual(['[', ']'])
  })

  it('其它类型 → null', () => {
    expect(getContainerMarkers('businessObject')).toBe(null)
    expect(getContainerMarkers(undefined)).toBe(null)
  })
})

describe('nodeLabelTemplate.collapseFormatMarker', () => {
  it('domain 折叠标题', () => {
    expect(collapseFormatMarker('domain', 'SCM', '供应链云')).toBe('<供应链云>\\n领域 SCM')
  })

  it('subdomain 折叠标题', () => {
    expect(collapseFormatMarker('subdomain', 'SCP', '供应链计划')).toBe('{供应链计划}\\n子领域 SCP')
  })

  it('servicemodule 折叠标题', () => {
    expect(collapseFormatMarker('servicemodule', 'DP', '需求计划')).toBe('[需求计划]\\n服务模块 DP')
  })

  it('无编码或名称时返回空串', () => {
    expect(collapseFormatMarker('domain', '', '名称')).toBe('')
    expect(collapseFormatMarker('domain', 'X', '')).toBe('')
  })

  it('无法识别类型时返回空串', () => {
    expect(collapseFormatMarker('businessObject', 'X', '名称')).toBe('')
  })
})

describe('nodeLabelTemplate.businessObjectLabel', () => {
  it('有编码 → 名称\\n编码 两行', () => {
    expect(businessObjectLabel({ name: '采购订单', code: 'PO201' })).toBe('采购订单\\nPO201')
  })

  it('优先 originalName', () => {
    expect(businessObjectLabel({ name: '旧名', originalName: '新名', code: 'A' })).toBe('新名\\nA')
  })

  it('无编码 → 仅名称', () => {
    expect(businessObjectLabel({ name: '采购订单' })).toBe('采购订单')
  })

  it('中心标记经 opts 传入', () => {
    expect(businessObjectLabel({ name: '采购订单', code: 'PO201' }, { centerMark: '◆' })).toBe('◆采购订单\\nPO201')
  })

  it('可自定义分隔符', () => {
    expect(businessObjectLabel({ name: '采购订单', code: 'PO201' }, { separator: ' · ' })).toBe('采购订单 · PO201')
  })

  it('兼容 nodeCode 字段 (deprecated blockDiagram 路径)', () => {
    expect(businessObjectLabel({ name: '采购订单', nodeCode: 'PO201' })).toBe('采购订单\\nPO201')
  })

  it('无名称时返回空串', () => {
    expect(businessObjectLabel({ code: 'X' })).toBe('')
  })
})
