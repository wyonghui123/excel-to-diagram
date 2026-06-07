/**
 * Safe Expression Evaluator
 *
 * Replaces `new Function()` for evaluating YAML-defined condition expressions.
 * Based on exhaustive analysis of all actual expressions in the codebase:
 *   - "row.is_current !== true"
 *   - "record.status === 'draft'"
 *   - "record.status === 'approved'"
 *
 * Design principles:
 *   - Whitelist operators only (===, !==, ==, !=, >, <, >=, <=)
 *   - Block prototype chain access (__proto__, constructor, prototype)
 *   - Fail-open: return true on parse errors to avoid hiding UI elements
 *   - Zero external dependencies
 */

const FORBIDDEN_PATH_SEGMENTS = new Set([
  '__proto__', 'constructor', 'prototype',
  '__defineGetter__', '__defineSetter__', '__lookupGetter__', '__lookupSetter__',
])

const COMPARISON_OPS = ['===', '!==', '==', '!=', '>=', '<=', '>', '<']

function resolvePath(path, record, prefix) {
  if (typeof path !== 'string') return undefined
  path = path.trim()

  const cleanPath = path
    .replace(new RegExp('^' + escapeRegex(prefix) + '\\.'), '')
    .replace(/^record\./, '')
    .replace(/^self\./, '')

  const parts = cleanPath.split('.')
  for (const part of parts) {
    if (FORBIDDEN_PATH_SEGMENTS.has(part)) {
      throw new Error('Forbidden path access: ' + part)
    }
  }

  let value = record
  for (const part of parts) {
    if (value === null || value === undefined) return undefined
    value = value[part]
  }
  return value
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function resolveLiteral(str) {
  if (typeof str !== 'string') return str
  str = str.trim()
  if (str === 'true') return true
  if (str === 'false') return false
  if (str === 'null') return null
  if (str === 'undefined') return undefined
  if ((str.startsWith("'") && str.endsWith("'")) ||
      (str.startsWith('"') && str.endsWith('"'))) {
    return str.slice(1, -1)
  }
  const num = Number(str)
  if (!isNaN(num) && str !== '') return num
  return str
}

function findComparisonOp(expr) {
  for (let end = expr.length - 1; end >= 0; end--) {
    if (expr[end] === "'" || expr[end] === '"') {
      const quote = expr[end]
      end--
      while (end >= 0 && expr[end] !== quote) end--
      continue
    }
    const twoChar = expr.substring(end - 1, end + 1)
    if (twoChar === '==' || twoChar === '!=') {
      if (end >= 2) {
        const threeChar = expr.substring(end - 2, end + 1)
        if (threeChar === '===' || threeChar === '!==') {
          return { op: threeChar, index: end - 2 }
        }
      }
      return { op: twoChar, index: end - 1 }
    }
    if (twoChar === '>=' || twoChar === '<=') {
      return { op: twoChar, index: end - 1 }
    }
    const oneChar = expr[end]
    if (oneChar === '>' || oneChar === '<') {
      return { op: oneChar, index: end }
    }
  }
  return null
}

function compare(left, op, right) {
  switch (op) {
    case '===': return left === right
    case '!==': return left !== right
    case '==': return left == right
    case '!=': return left != right
    case '>': return left > right
    case '<': return left < right
    case '>=': return left >= right
    case '<=': return left <= right
    default: return true
  }
}

/**
 * Evaluate a YAML-defined condition expression against a record.
 *
 * @param {string} expr - The condition expression (e.g. "row.is_current !== true")
 * @param {object} record - The data record to evaluate against
 * @param {string} [prefix='row'] - Variable prefix used in the expression
 * @returns {boolean} Evaluation result. Returns true on error (fail-open).
 */
export function evaluateCondition(expr, record, prefix) {
  if (!expr || typeof expr !== 'string') return true
  const trimmed = expr.trim()
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  if (!record || typeof record !== 'object') return true

  prefix = prefix || 'row'

  try {
    let working = trimmed
    let negate = false

    if (working.startsWith('!')) {
      negate = true
      working = working.substring(1).trim()
    }

    const opInfo = findComparisonOp(working)

    if (opInfo) {
      const leftPath = working.substring(0, opInfo.index).trim()
      const rightRaw = working.substring(opInfo.index + opInfo.op.length).trim()

      const leftValue = resolvePath(leftPath, record, prefix)
      const rightValue = resolveLiteral(rightRaw)

      const result = compare(leftValue, opInfo.op, rightValue)
      return negate ? !result : result
    }

    const value = resolvePath(working, record, prefix)
    return negate ? !value : !!value
  } catch (e) {
    console.warn('[safeExpression] Evaluation failed for "' + trimmed + '":', e.message)
    return true
  }
}

export default evaluateCondition
