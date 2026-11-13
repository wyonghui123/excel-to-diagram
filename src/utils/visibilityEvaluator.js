/**
 * visibilityEvaluator.js - visible_when 求值器（T13-7）
 *
 * 语义约定（§13.5）：
 *   - 表达式缺省（undefined / null / 空串）=> 字段默认可见（true）
 *   - 求值失败 / 表达式无法解析 => fail-closed（false），并且同一表达式只告警一次
 *   - 求值完全复用 safeExpression 的白名单子集，不重复实现解释器
 */

import { evaluateCondition } from '@/utils/safeExpression'
import { logger } from '@/utils/logger'

// 已告警过的表达式（模块级，避免同一字段每次渲染都刷日志）
const warnedExpressions = new Set()

/**
 * safeExpression 内部用 try/catch 吞掉异常并直接返回 false，
 * 导致调用方无法区分「条件为假」和「表达式非法」，也就无法 fail-closed 告警。
 * 这里只做一层极轻量的语法白名单校验：出现 safeExpression 不支持的语法即视为无法解析。
 */
const UNSUPPORTED_SYNTAX = /(&&|\|\||=>|[(){};]|\bnew\b|\bfunction\b|\btypeof\b)/

/** 去掉字符串字面量，避免把字面量里的括号/分号误判为非法语法 */
function stripQuotedLiterals(expr) {
  return expr.replace(/'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/g, "''")
}

function warnOnce(expr, error) {
  const key = String(expr)
  if (warnedExpressions.has(key)) return
  warnedExpressions.add(key)
  logger.warn(
    '[visible_when] 表达式求值失败，字段隐藏（fail-closed）:',
    key,
    error ? error.message : ''
  )
}

/**
 * 求值 visible_when 表达式
 *
 * @param {string|undefined|null} expr - visible_when 表达式
 * @param {object} data - 当前表单数据，直接作为字段作用域
 * @returns {boolean} 字段是否可见（异常/无法解析时 false）
 */
export function evaluateVisibleWhen(expr, data) {
  if (expr === undefined || expr === null) return true
  if (typeof expr !== 'string') {
    warnOnce(expr)
    return false
  }
  const trimmed = expr.trim()
  if (!trimmed) return true

  if (UNSUPPORTED_SYNTAX.test(stripQuotedLiterals(trimmed))) {
    warnOnce(trimmed)
    return false
  }

  try {
    return Boolean(evaluateCondition(trimmed, data || {}))
  } catch (error) {
    warnOnce(trimmed, error)
    return false
  }
}

/** 清空告警去重缓存（仅测试使用） */
export function _resetVisibilityWarnCache() {
  warnedExpressions.clear()
}

export default evaluateVisibleWhen