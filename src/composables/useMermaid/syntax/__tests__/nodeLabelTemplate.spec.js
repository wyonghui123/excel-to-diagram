import { describe, it, expect } from 'vitest'
import {
  extractOwnGroupName,
  getContainerMarkers,
  collapseFormatMarker,
  businessObjectLabel,
  escapeMermaidLabelText
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

  it('内部 name/code 含特殊字符时转义为 mermaid #XX;, 保留容器标记 (2026-08-21)', () => {
    expect(collapseFormatMarker('domain', 'SCM', '销售<折扣>')).toBe('<销售#60;折扣#62;>\\n领域 SCM')
    expect(collapseFormatMarker('servicemodule', 'D"P', '需求&计划')).toBe('[需求#38;计划]\\n服务模块 D#quot;P')
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

describe('nodeLabelTemplate.escapeMermaidLabelText (2026-08-21 mermaid 原生 #XX; 转义)', () => {
  it('普通文本不变 (no-op)', () => {
    expect(escapeMermaidLabelText('采购订单')).toBe('采购订单')
    expect(escapeMermaidLabelText('PO201')).toBe('PO201')
    expect(escapeMermaidLabelText('')).toBe('')
  })

  it('null/undefined 返回空串', () => {
    expect(escapeMermaidLabelText(null)).toBe('')
    expect(escapeMermaidLabelText(undefined)).toBe('')
  })

  it('转义 & < > " 为 mermaid #XX;', () => {
    expect(escapeMermaidLabelText('<img onerror=x>')).toBe('#60;img onerror=x#62;')
    expect(escapeMermaidLabelText('a&b')).toBe('a#38;b')
    expect(escapeMermaidLabelText('say "hi"')).toBe('say #quot;hi#quot;')
  })

  it('单引号/反斜杠/方括号也转义 (与 release sanitizeMermaidLabel 一致)', () => {
    expect(escapeMermaidLabelText("it's [x]")).toBe('it#apos;s #91;x#93;')
    expect(escapeMermaidLabelText('a\\b')).toBe('a#92;b')
  })

  it('顺序正确: 先 & 避免二次转义', () => {
    expect(escapeMermaidLabelText('&lt;')).toBe('#38;lt;')
  })

  it('字面反斜杠 n 会被转义为 #92;n (release sanitizeMermaidLabel 语义)', () => {
    expect(escapeMermaidLabelText('名称\\n编码')).toBe('名称#92;n编码')
  })
})

describe('nodeLabelTemplate.businessObjectLabel XSS 转义 (2026-08-21 mermaid #XX;)', () => {
  it('含 < 的名称转义为 #60;', () => {
    expect(businessObjectLabel({ name: '销售<折扣>', code: 'S1' })).toBe('销售#60;折扣#62;\\nS1')
  })

  it('含 " 的编码转义为 #quot;', () => {
    expect(businessObjectLabel({ name: '订单', code: 'O"1' })).toBe('订单\\nO#quot;1')
  })

  it('含 & 的名称转义为 #38;', () => {
    expect(businessObjectLabel({ name: 'R&D', code: 'R1' })).toBe('R#38;D\\nR1')
  })
})
