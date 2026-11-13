/**
 * useBatchActions.spec.js - T13-6 批量动作求值 composable
 *
 * 验证：50ms 窗口合并、pending/evaluate_failed fail-closed、verdict 缓存与 clear。
 */

/* eslint-disable max-lines-per-function -- 测试文件 describe 块按场景分组，可读性 > 单函数行数 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/services/boService', () => {
  const boService = { evaluateActions: vi.fn() }
  return { boService, default: boService }
})

vi.mock('@/utils/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }
}))

import { useBatchActions } from '@/composables/useBatchActions'
import { boService } from '@/services/boService'
import { logger } from '@/utils/logger'

const PENDING = { enabled: false, reason: 'pending', required_permission: '' }

const ACTIONS = [
  { id: 'edit', permission: 'demo:edit' },
  { id: 'delete', permission: 'demo:delete', condition: "self.status == 'draft'" },
  { id: 'view' }
]

async function flushMicrotasks(times = 6) {
  for (let i = 0; i < times; i += 1) {
    await Promise.resolve()
  }
}

describe('useBatchActions 批量动作求值（T13-6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('50ms 窗口内 2 行 3 动作合并为一次请求，body 正确', async () => {
    boService.evaluateActions.mockResolvedValue({ success: true, data: {} })
    const batch = useBatchActions('demo')

    for (const id of [1, 2]) {
      for (const action of ACTIONS) {
        expect(batch.getAction(id, action)).toEqual(PENDING)
      }
    }
    // 窗口未到 → 不发请求
    expect(boService.evaluateActions).not.toHaveBeenCalled()

    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    expect(boService.evaluateActions).toHaveBeenCalledTimes(1)
    const [objectType, ids, actions] = boService.evaluateActions.mock.calls[0]
    expect(objectType).toBe('demo')
    expect(ids).toEqual(['1', '2'])
    expect(actions).toEqual([
      { id: 'edit', permission: 'demo:edit', condition: '' },
      { id: 'delete', permission: 'demo:delete', condition: "self.status == 'draft'" },
      { id: 'view', permission: '', condition: '' }
    ])
  })

  it('请求未返回期间该 id 的所有动作都返回 pending，且不重复发请求', async () => {
    let resolveRequest
    boService.evaluateActions.mockImplementation(() => new Promise((resolve) => {
      resolveRequest = resolve
    }))
    const batch = useBatchActions('demo')

    batch.getAction(1, ACTIONS[0])
    batch.getAction(1, ACTIONS[1])
    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    expect(batch.getAction(1, ACTIONS[0])).toEqual(PENDING)
    expect(batch.getAction(1, ACTIONS[2])).toEqual(PENDING)
    expect(boService.evaluateActions).toHaveBeenCalledTimes(1)

    resolveRequest({ success: true, data: { 1: { edit: { enabled: true, reason: '' } } } })
    await flushMicrotasks()

    expect(batch.getAction(1, ACTIONS[0]).enabled).toBe(true)
  })

  it('命中 verdict 时返回缓存结果，缺失 verdict 按 unsupported fail-closed', async () => {
    boService.evaluateActions.mockResolvedValue({
      success: true,
      data: {
        1: { edit: { enabled: true, reason: '', required_permission: 'demo:edit' } },
        2: { edit: { enabled: false, reason: 'no_permission', required_permission: 'demo:edit' } }
      }
    })
    const batch = useBatchActions('demo')

    batch.getAction(1, { id: 'edit' })
    batch.getAction(2, { id: 'edit' })
    batch.getAction(1, { id: 'delete' })
    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    expect(batch.getAction(1, { id: 'edit' })).toEqual({
      enabled: true, reason: '', required_permission: 'demo:edit'
    })
    expect(batch.getAction(2, { id: 'edit' }).reason).toBe('no_permission')
    expect(batch.getAction(1, { id: 'delete' })).toEqual({
      enabled: false, reason: 'unsupported', required_permission: ''
    })
  })

  it('请求抛异常时整批 evaluate_failed，并只记录一次 logger.error', async () => {
    boService.evaluateActions.mockRejectedValue(new Error('500'))
    const batch = useBatchActions('demo')

    batch.getAction(1, ACTIONS[0])
    batch.getAction(2, ACTIONS[0])
    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    expect(batch.getAction(1, ACTIONS[0])).toEqual({
      enabled: false, reason: 'evaluate_failed', required_permission: ''
    })
    expect(batch.getAction(2, ACTIONS[0])).toEqual({
      enabled: false, reason: 'evaluate_failed', required_permission: ''
    })
    expect(logger.error).toHaveBeenCalledTimes(1)
  })

  it('接口 success=false 同样整批 fail-closed', async () => {
    boService.evaluateActions.mockResolvedValue({ success: false, message: 'BOOM' })
    const batch = useBatchActions('demo')

    batch.getAction(1, ACTIONS[0])
    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    expect(batch.getAction(1, ACTIONS[0]).reason).toBe('evaluate_failed')
    expect(logger.error).toHaveBeenCalledTimes(1)
  })

  it('对象级动作使用 _object 桶，发送空 ids', async () => {
    boService.evaluateActions.mockResolvedValue({
      success: true,
      data: { _object: { export: { enabled: true, reason: '' } } }
    })
    const batch = useBatchActions('demo')

    expect(batch.getAction('_object', { id: 'export' })).toEqual(PENDING)
    vi.advanceTimersByTime(50)
    await flushMicrotasks()

    const [, ids] = boService.evaluateActions.mock.calls[0]
    expect(ids).toEqual([])
    expect(batch.getAction('_object', { id: 'export' }).enabled).toBe(true)
  })

  it('clear() 清空缓存后重新排队', async () => {
    boService.evaluateActions.mockResolvedValue({
      success: true,
      data: { 1: { edit: { enabled: true, reason: '' } } }
    })
    const batch = useBatchActions('demo')

    batch.getAction(1, { id: 'edit' })
    vi.advanceTimersByTime(50)
    await flushMicrotasks()
    expect(batch.getAction(1, { id: 'edit' }).enabled).toBe(true)

    batch.clear()
    expect(batch.getAction(1, { id: 'edit' })).toEqual(PENDING)

    vi.advanceTimersByTime(50)
    await flushMicrotasks()
    expect(boService.evaluateActions).toHaveBeenCalledTimes(2)
  })
})