import { describe, it, expect } from 'vitest'
import { normalizeValidationErrors } from '../validationErrors'

describe('normalizeValidationErrors', () => {
  it('按 field_id 归集字段文案并去重', () => {
    const result = {
      success: false,
      errors: [
        { field_id: 'code', field_name: '编码', rule: 'required', message: '编码 不能为空' },
        { field_id: 'code', field_name: '编码', rule: 'required', message: '编码 不能为空' },
        { field_id: 'qty', field_name: '数量', rule: 'numeric_min', message: '数量 不能小于 1' }
      ]
    }

    const { fieldErrors, messages } = normalizeValidationErrors(result)

    expect(fieldErrors).toEqual({
      code: '编码 不能为空',
      qty: '数量 不能小于 1'
    })
    expect(messages).toEqual(['编码 不能为空', '数量 不能小于 1'])
  })

  it('缺少 field_id 时回退 field_name，旧式 details 兼容', () => {
    const result = {
      details: [
        { field_name: 'currency_id', rule: 'required', message: '币种 不能为空' }
      ]
    }

    const { fieldErrors } = normalizeValidationErrors(result)
    expect(fieldErrors.currency_id).toBe('币种 不能为空')
  })

  it('errors 优先于 details，空结果返回空结构', () => {
    expect(normalizeValidationErrors(null)).toEqual({ fieldErrors: {}, messages: [] })
    expect(normalizeValidationErrors({ errors: [] })).toEqual({ fieldErrors: {}, messages: [] })

    const result = {
      errors: [{ field_id: 'name', message: '名称 不能为空' }],
      details: [{ field_id: 'other', message: '不应被使用' }]
    }
    const { fieldErrors } = normalizeValidationErrors(result)
    expect(fieldErrors).toEqual({ name: '名称 不能为空' })
  })

  it('忽略无消息项与非对象项', () => {
    const result = {
      errors: [null, 'bad', { field_id: 'x' }, { field_id: 'y', message: '错误' }]
    }
    const { fieldErrors, messages } = normalizeValidationErrors(result)
    expect(fieldErrors).toEqual({ y: '错误' })
    expect(messages).toEqual(['错误'])
  })
})