/**
 * configValidator 单元测试
 * 目标: 覆盖 ConfigValidator 类的核心方法 (validateCrossTableFilters / validateAndLog / validateSingleFilter / getErrorSummary)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ConfigValidator, { ConfigValidator as NamedConfigValidator } from '../configValidator.js'

describe('configValidator', () => {
  describe('exports', () => {
    it('default export 和 named export 应指向同一对象', () => {
      expect(ConfigValidator).toBe(NamedConfigValidator)
      expect(typeof ConfigValidator).toBe('object')
    })

    it('应暴露核心方法: validateCrossTableFilters / validateAndLog / validateSingleFilter / getErrorSummary', () => {
      expect(typeof ConfigValidator.validateCrossTableFilters).toBe('function')
      expect(typeof ConfigValidator.validateAndLog).toBe('function')
      expect(typeof ConfigValidator.validateSingleFilter).toBe('function')
      expect(typeof ConfigValidator.getErrorSummary).toBe('function')
    })
  })

  describe('validateCrossTableFilters - happy path', () => {
    it('完全合法的配置应该通过验证', () => {
      const config = [
        {
          id: 'filter_001',
          display_name: '客户过滤器',
          association: {
            target_table: 'customer',
            target_alias: 'c',
            join_type: 'left',
            on_conditions: [
              { left_field: 'customer_id', operator: 'eq', right_field: 'c.id' }
            ]
          },
          ui: {
            filter_type: 'select',
            options_source: 'static',
            static_options: [{ value: 'A', label: 'A' }],
            position: 0
          }
        }
      ]

      const result = ConfigValidator.validateCrossTableFilters(config)
      expect(result.valid).toBe(true)
      expect(result.errors).toEqual([])
      // 显示 display_name 在 happy path 中已提供, 不应产生关于 display_name 的 warning
      expect(result.warnings.some(w => w.includes('display_name'))).toBe(false)
    })

    it('api options_source 需要 api_endpoint', () => {
      const config = [
        {
          id: 'f1',
          association: {
            target_table: 't',
            on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }]
          },
          ui: {
            filter_type: 'select',
            options_source: 'api',
            api_endpoint: '/api/x'
          }
        }
      ]
      const result = ConfigValidator.validateCrossTableFilters(config)
      expect(result.valid).toBe(true)
    })
  })

  describe('validateCrossTableFilters - type & structure errors', () => {
    it('非数组输入应返回 valid=false 和一个错误', () => {
      const result = ConfigValidator.validateCrossTableFilters('not-an-array')
      expect(result.valid).toBe(false)
      expect(result.errors).toContain('cross_table_filters must be an array')
      expect(result.warnings).toEqual([])
    })

    it('null 输入应返回 valid=false', () => {
      const result = ConfigValidator.validateCrossTableFilters(null)
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(0)
    })

    it('undefined 输入应返回 valid=false', () => {
      const result = ConfigValidator.validateCrossTableFilters(undefined)
      expect(result.valid).toBe(false)
    })

    it('空数组应通过验证 (无错误, 无警告)', () => {
      const result = ConfigValidator.validateCrossTableFilters([])
      expect(result.valid).toBe(true)
      expect(result.errors).toEqual([])
      expect(result.warnings).toEqual([])
    })
  })

  describe('validateCrossTableFilters - field validation', () => {
    it('缺少 id 应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        { association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] } }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('id'))).toBe(true)
    })

    it('id 不是字符串应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        { id: 123, association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] } }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('id must be a string'))).toBe(true)
    })

    it('缺少 display_name 应产生警告但不使 valid=false', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] }
        }
      ])
      expect(result.valid).toBe(true)
      expect(result.warnings.some(w => w.includes('display_name'))).toBe(true)
    })

    it('association 缺失应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([{ id: 'f1' }])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('association'))).toBe(true)
    })

    it('join_type 非法值应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: {
            target_table: 't',
            join_type: 'cross',
            on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }]
          }
        }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('join_type'))).toBe(true)
    })

    it('on_conditions 为空数组应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        { id: 'f1', association: { target_table: 't', on_conditions: [] } }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('on_conditions cannot be empty'))).toBe(true)
    })

    it('on_conditions 中非法 operator 应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: {
            target_table: 't',
            on_conditions: [{ left_field: 'a', operator: '~', right_field: 'b' }]
          }
        }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('Invalid operator'))).toBe(true)
    })

    it('ui.filter_type 非法值应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] },
          ui: { filter_type: 'slider', options_source: 'static', static_options: [{ v: 1 }] }
        }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('filter_type'))).toBe(true)
    })

    it('ui.options_source=static 缺少 static_options 应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] },
          ui: { filter_type: 'select', options_source: 'static' }
        }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('static_options'))).toBe(true)
    })

    it('ui.options_source=enum 缺少 enum_type 应产生错误', () => {
      const result = ConfigValidator.validateCrossTableFilters([
        {
          id: 'f1',
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] },
          ui: { filter_type: 'select', options_source: 'enum' }
        }
      ])
      expect(result.valid).toBe(false)
      expect(result.errors.some(e => e.includes('enum_type'))).toBe(true)
    })
  })

  describe('validateAndLog', () => {
    let errorSpy
    let warnSpy
    let logSpy

    beforeEach(() => {
      errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    })

    afterEach(() => {
      errorSpy.mockRestore()
      warnSpy.mockRestore()
      logSpy.mockRestore()
    })

    it('验证通过时输出 console.log 且不输出 error/warn', () => {
      const config = [
        {
          id: 'f1',
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] }
        }
      ]
      const result = ConfigValidator.validateAndLog(config, 'test_config')
      expect(result.valid).toBe(true)
      expect(logSpy).toHaveBeenCalled()
      expect(errorSpy).not.toHaveBeenCalled()
    })

    it('验证失败时输出 console.error', () => {
      const result = ConfigValidator.validateAndLog(null, 'bad')
      expect(result.valid).toBe(false)
      expect(errorSpy).toHaveBeenCalled()
      expect(errorSpy.mock.calls[0][0]).toContain('bad')
    })

    it('有警告时输出 console.warn', () => {
      const config = [
        {
          id: 'f1',
          // 缺 display_name -> warning
          association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] }
        }
      ]
      ConfigValidator.validateAndLog(config, 'cfg')
      expect(warnSpy).toHaveBeenCalled()
    })
  })

  describe('validateSingleFilter', () => {
    it('应接受单个 filter 对象并复用数组验证逻辑', () => {
      const filter = {
        id: 'f1',
        association: { target_table: 't', on_conditions: [{ left_field: 'a', operator: 'eq', right_field: 'b' }] }
      }
      const result = ConfigValidator.validateSingleFilter(filter)
      expect(result.valid).toBe(true)
    })

    it('非法的单 filter 应报告错误', () => {
      const result = ConfigValidator.validateSingleFilter({})
      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(0)
    })
  })

  describe('getErrorSummary', () => {
    it('valid=true 时返回 "No errors"', () => {
      const result = { valid: true, errors: [], warnings: [] }
      expect(ConfigValidator.getErrorSummary(result)).toBe('No errors')
    })

    it('包含错误时应输出 "Errors (N):" 列表', () => {
      const result = { valid: false, errors: ['e1', 'e2'], warnings: [] }
      const summary = ConfigValidator.getErrorSummary(result)
      expect(summary).toContain('Errors (2)')
      expect(summary).toContain('- e1')
      expect(summary).toContain('- e2')
    })

    it('包含警告时同时输出警告段', () => {
      const result = { valid: false, errors: ['e1'], warnings: ['w1'] }
      const summary = ConfigValidator.getErrorSummary(result)
      expect(summary).toContain('Errors (1)')
      expect(summary).toContain('Warnings (1)')
      expect(summary).toContain('- w1')
    })
  })
})
