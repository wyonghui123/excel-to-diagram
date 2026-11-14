import { describe, it, expect } from 'vitest'
import {
  buildDefaults,
  isSecretKey,
  schemaToFields,
  stripRedacted,
  toEpochSeconds
} from '../jobParams'

const SCHEMA = {
  type: 'object',
  required: ['action_id'],
  properties: {
    action_id: { type: 'string', title: '动作' },
    count: { type: 'integer', default: 10 },
    dry_run: { type: 'boolean' },
    mode: {
      type: 'string',
      enum: ['full', 'fast'],
      'x-ui': { enum_labels: { full: '全量', fast: '快速' } }
    },
    password: { type: 'string' },
    token_ttl: { type: 'string', 'x-ui': { secret: true } },
    region: { type: 'string', const: 'cn' },
    note: { type: 'string', description: '备注说明' }
  }
}

describe('jobParams', () => {
  it('schema 为空 / 非对象时返回空表单', () => {
    expect(schemaToFields(null)).toEqual([])
    expect(schemaToFields({})).toEqual([])
    expect(schemaToFields([])).toEqual([])
    expect(buildDefaults(null, { a: 1 })).toEqual({})
  })

  it('按元数据映射控件类型', () => {
    const fields = schemaToFields(SCHEMA)
    const byKey = Object.fromEntries(fields.map((f) => [f.key, f]))

    expect(byKey.action_id.type).toBe('text')
    expect(byKey.action_id.required).toBe(true)
    expect(byKey.action_id.label).toBe('动作')

    expect(byKey.count.type).toBe('number')
    expect(byKey.dry_run.type).toBe('switch')
    expect(byKey.mode.type).toBe('select')
    expect(byKey.mode.options).toEqual([
      { label: '全量', value: 'full' },
      { label: '快速', value: 'fast' }
    ])
    expect(byKey.password.type).toBe('password')
    expect(byKey.token_ttl.type).toBe('password')
    expect(byKey.region.type).toBe('text')
    expect(byKey.region.disabled).toBe(true)
    expect(byKey.note.placeholder).toBe('备注说明')
  })

  it('isSecretKey 与后端规则一致（子串匹配）', () => {
    expect(isSecretKey('password')).toBe(true)
    expect(isSecretKey('API_TOKEN')).toBe(true)
    expect(isSecretKey('access_key')).toBe(true)
    expect(isSecretKey('note')).toBe(false)
    expect(isSecretKey('')).toBe(false)
  })

  it('buildDefaults 显式值优先于 schema.default', () => {
    expect(buildDefaults(SCHEMA, { count: 3 })).toEqual({ count: 3 })
    expect(buildDefaults(SCHEMA)).toEqual({ count: 10 })
    expect(buildDefaults(SCHEMA, { unknown: 1 })).toEqual({ count: 10 })
  })

  it('stripRedacted 剔除脱敏占位，保留其它值', () => {
    expect(stripRedacted({ password: '***', note: 'n', count: 0 }))
      .toEqual({ note: 'n', count: 0 })
    expect(stripRedacted(null)).toEqual({})
    expect(stripRedacted(['x'])).toEqual({})
  })

  it('toEpochSeconds 接受 epoch / Date / ISO，其它返回 null', () => {
    expect(toEpochSeconds(1800000000)).toBe(1800000000)
    expect(toEpochSeconds('1800000000')).toBe(1800000000)
    expect(toEpochSeconds(new Date(1800000000 * 1000))).toBe(1800000000)
    const iso = '2026-11-14T00:00:00.000Z'
    expect(toEpochSeconds(iso)).toBe(Math.floor(Date.parse(iso) / 1000))
    expect(toEpochSeconds(null)).toBeNull()
    expect(toEpochSeconds('')).toBeNull()
    expect(toEpochSeconds('not-a-date')).toBeNull()
  })
})