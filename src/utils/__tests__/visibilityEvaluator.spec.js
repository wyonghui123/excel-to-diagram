/**
 * visibilityEvaluator.spec.js - visible_when 求值器测试（T13-7）
 *
 * 覆盖：空表达式默认可见 / 条件命中与不命中 / 非法表达式 fail-closed 且只告警一次 /
 *       数据缺字段不抛异常。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { logger } from '@/utils/logger'
import {
  evaluateVisibleWhen,
  _resetVisibilityWarnCache
} from '@/utils/visibilityEvaluator'

describe('visibilityEvaluator', () => {
  let warnSpy

  beforeEach(() => {
    _resetVisibilityWarnCache()
    warnSpy = vi.spyOn(logger, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    warnSpy.mockRestore()
  })

  it('空表达式默认可见', () => {
    expect(evaluateVisibleWhen(undefined, {})).toBe(true)
    expect(evaluateVisibleWhen(null, {})).toBe(true)
    expect(evaluateVisibleWhen('', {})).toBe(true)
    expect(evaluateVisibleWhen('   ', {})).toBe(true)
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it("status === 'draft' 命中返回 true，不命中返回 false", () => {
    expect(evaluateVisibleWhen("status === 'draft'", { status: 'draft' })).toBe(true)
    expect(evaluateVisibleWhen("status === 'draft'", { status: 'approved' })).toBe(false)
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('支持 and / or / in 组合表达式', () => {
    const data = { status: 'draft', kind: 'normal' }
    expect(evaluateVisibleWhen("status === 'draft' and kind === 'normal'", data)).toBe(true)
    expect(evaluateVisibleWhen("status === 'approved' or kind === 'normal'", data)).toBe(true)
    expect(evaluateVisibleWhen("status in ['draft', 'pending']", data)).toBe(true)
  })

  it('非法表达式 fail-closed，同一表达式只告警一次', () => {
    const data = { status: 'draft', name: 'x' }

    expect(evaluateVisibleWhen('status && name', data)).toBe(false)
    expect(warnSpy).toHaveBeenCalledTimes(1)

    // 同一表达式重复求值不再刷日志
    expect(evaluateVisibleWhen('status && name', data)).toBe(false)
    expect(warnSpy).toHaveBeenCalledTimes(1)

    // 另一个非法表达式单独告警
    expect(evaluateVisibleWhen("(status === 'draft')", data)).toBe(false)
    expect(warnSpy).toHaveBeenCalledTimes(2)
  })

  it('数据缺字段不抛异常，按不命中处理', () => {
    expect(() => evaluateVisibleWhen("missing === 'x'", {})).not.toThrow()
    expect(evaluateVisibleWhen("missing === 'x'", {})).toBe(false)
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('非字符串表达式 fail-closed', () => {
    expect(evaluateVisibleWhen(123, {})).toBe(false)
    expect(warnSpy).toHaveBeenCalledTimes(1)
  })
})