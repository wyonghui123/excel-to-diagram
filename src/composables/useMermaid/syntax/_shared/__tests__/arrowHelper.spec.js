/**
 * @file arrowHelper.spec.js
 * @description [v34 双向支持] 关系箭头生成辅助函数测试
 */
import { describe, it, expect } from 'vitest'
import { getArrowSyntax, sanitizeLabel, isBidirectionalLink } from '../arrowHelper.js'

describe('arrowHelper - getArrowSyntax', () => {
  it('单向 (推) 无 label', () => {
    const result = getArrowSyntax('A', 'B', '', { relationDirection: '推' })
    expect(result).toBe('  A --> B\n')
  })

  it('单向 (拉) 无 label', () => {
    const result = getArrowSyntax('A', 'B', '', { relationDirection: '拉' })
    expect(result).toBe('  A --> B\n')
  })

  it('单向 (无 direction) 无 label - 默认单向', () => {
    const result = getArrowSyntax('A', 'B', '', {})
    expect(result).toBe('  A --> B\n')
  })

  it('单向 (direction undefined) 无 label', () => {
    const result = getArrowSyntax('A', 'B', '', { relationDirection: undefined })
    expect(result).toBe('  A --> B\n')
  })

  it('单向 (direction 空字符串) 无 label', () => {
    const result = getArrowSyntax('A', 'B', '', { relationDirection: '' })
    expect(result).toBe('  A --> B\n')
  })

  it('单向 有 label', () => {
    const result = getArrowSyntax('A', 'B', 'REL_001', { relationDirection: '推' })
    expect(result).toBe('  A -->|"REL_001"| B\n')
  })

  it('双向 无 label → <-->', () => {
    const result = getArrowSyntax('A', 'B', '', { relationDirection: '双向' })
    expect(result).toBe('  A <--> B\n')
  })

  it('双向 有 label → <-- text -->', () => {
    const result = getArrowSyntax('A', 'B', 'REL_001', { relationDirection: '双向' })
    expect(result).toBe('  A <-- REL_001 --> B\n')
  })

  it('双向 label 含特殊字符 (| → /)', () => {
    const result = getArrowSyntax('A', 'B', 'X|Y|Z', { relationDirection: '双向' })
    expect(result).toBe('  A <-- X/Y/Z --> B\n')
  })

  it('双向 label 含换行', () => {
    const result = getArrowSyntax('A', 'B', 'line1\nline2', { relationDirection: '双向' })
    expect(result).toBe('  A <-- line1 line2 --> B\n')
  })

  it('link 为 null 不抛错 (按单向处理)', () => {
    const result = getArrowSyntax('A', 'B', '', null)
    expect(result).toBe('  A --> B\n')
  })

  it('link 为 undefined 不抛错 (按单向处理)', () => {
    const result = getArrowSyntax('A', 'B', '', undefined)
    expect(result).toBe('  A --> B\n')
  })

  it('label 为 null / undefined 视为空', () => {
    const r1 = getArrowSyntax('A', 'B', null, { relationDirection: '推' })
    const r2 = getArrowSyntax('A', 'B', undefined, { relationDirection: '推' })
    expect(r1).toBe('  A --> B\n')
    expect(r2).toBe('  A --> B\n')
  })
})

describe('arrowHelper - sanitizeLabel', () => {
  it('空值', () => {
    expect(sanitizeLabel('')).toBe('')
    expect(sanitizeLabel(null)).toBe('')
    expect(sanitizeLabel(undefined)).toBe('')
  })

  it('去除前后空白', () => {
    expect(sanitizeLabel('  REL_001  ')).toBe('REL_001')
  })

  it('\| 替换为 /', () => {
    expect(sanitizeLabel('A|B|C')).toBe('A/B/C')
  })

  it('换行替换为空格', () => {
    expect(sanitizeLabel('line1\nline2')).toBe('line1 line2')
    expect(sanitizeLabel('line1\r\nline2')).toBe('line1 line2')
  })

  it('" 替换为 \'', () => {
    expect(sanitizeLabel('text "quoted"')).toBe("text 'quoted'")
  })

  it('全部规则组合', () => {
    expect(sanitizeLabel('  A|B\nC"D  ')).toBe('A/B C\'D')
  })
})

describe('arrowHelper - isBidirectionalLink', () => {
  it('双向 link 判定为 true', () => {
    expect(isBidirectionalLink({ relationDirection: '双向' })).toBe(true)
  })

  it('单向 link 判定为 false', () => {
    expect(isBidirectionalLink({ relationDirection: '推' })).toBe(false)
    expect(isBidirectionalLink({ relationDirection: '拉' })).toBe(false)
    expect(isBidirectionalLink({})).toBe(false)
  })

  it('null/undefined link 判定为 false (不抛错)', () => {
    expect(isBidirectionalLink(null)).toBe(false)
    expect(isBidirectionalLink(undefined)).toBe(false)
  })
})
