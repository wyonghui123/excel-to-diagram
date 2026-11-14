import { describe, it, expect } from 'vitest'
import {
  sourceLabel,
  statusLabel,
  statusTone,
  triggerTypeLabel
} from '../jobRunStatus'

describe('jobRunStatus', () => {
  it('覆盖后端 RUN_STATUSES 全集的文案', () => {
    const statuses = [
      'pending', 'claimed', 'running', 'retrying', 'succeeded',
      'failed', 'cancelled', 'skipped', 'dead'
    ]
    statuses.forEach((status) => {
      expect(statusLabel(status)).not.toBe(status)
      expect(statusTone(status)).not.toBe('default')
    })
  })

  it('未知状态回退原值（不猜测、不新增枚举）', () => {
    expect(statusLabel('weird')).toBe('weird')
    expect(statusLabel(null)).toBe('')
    expect(statusTone('weird')).toBe('default')
  })

  it('触发方式与来源文案齐备', () => {
    expect(triggerTypeLabel('cron')).toBe('定时')
    expect(triggerTypeLabel('interval')).toBe('周期')
    expect(triggerTypeLabel('once')).toBe('一次性')
    expect(sourceLabel('manual')).toBe('手动')
    expect(sourceLabel('import')).toBe('导入')
    expect(sourceLabel('scheduled')).toBe('计划')
    expect(sourceLabel('unknown')).toBe('unknown')
  })
})