import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn() },
  apiV2: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
}))

import { apiV2 } from '@/utils/httpClient'
import {
  cancelRun,
  createTrigger,
  deleteTrigger,
  fetchDispatcherStatus,
  fetchJobs,
  fetchRun,
  fetchRuns,
  fetchTriggers,
  patchJob,
  retryRun,
  runNow,
  updateTrigger
} from '../jobService'

describe('jobService', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetchJobs / patchJob 走作业定义端点', async () => {
    apiV2.get.mockResolvedValue({ success: true })
    apiV2.patch.mockResolvedValue({ success: true })
    await fetchJobs()
    expect(apiV2.get).toHaveBeenCalledWith('/jobs', { params: undefined })
    await patchJob('db_analyze', { status: 'paused' })
    expect(apiV2.patch).toHaveBeenCalledWith('/jobs/db_analyze', { status: 'paused' })
  })

  it('触发器 CRUD 的路径与 body 正确', async () => {
    apiV2.get.mockResolvedValue({ success: true })
    apiV2.post.mockResolvedValue({ success: true })
    apiV2.patch.mockResolvedValue({ success: true })
    apiV2.delete.mockResolvedValue({ success: true })

    await fetchTriggers('db_analyze')
    expect(apiV2.get).toHaveBeenCalledWith('/jobs/db_analyze/triggers')

    await createTrigger('db_analyze', { trigger_type: 'once', run_at: 1800000000 })
    expect(apiV2.post).toHaveBeenCalledWith('/jobs/db_analyze/triggers', {
      trigger_type: 'once', run_at: 1800000000
    })

    await updateTrigger(7, { enabled: false })
    expect(apiV2.patch).toHaveBeenCalledWith('/jobs/triggers/7', { enabled: false })

    await deleteTrigger(7)
    expect(apiV2.delete).toHaveBeenCalledWith('/jobs/triggers/7')
  })

  it('执行记录列表把过滤条件放进 params', async () => {
    apiV2.get.mockResolvedValue({ success: true })
    await fetchRuns({ status: 'failed', source: 'cron', page: 2 })
    expect(apiV2.get).toHaveBeenCalledWith('/jobs/runs', {
      params: { status: 'failed', source: 'cron', page: 2 }
    })
    await fetchRun(42)
    expect(apiV2.get).toHaveBeenCalledWith('/jobs/runs/42')
  })

  it('runNow / retryRun / cancelRun 均为 POST，空 body 用 {}', async () => {
    apiV2.post.mockResolvedValue({ success: true })
    await runNow('db_analyze')
    expect(apiV2.post).toHaveBeenCalledWith('/jobs/db_analyze/run-now', {})
    await retryRun(42)
    expect(apiV2.post).toHaveBeenCalledWith('/jobs/runs/42/retry', {})
    await cancelRun(42)
    expect(apiV2.post).toHaveBeenCalledWith('/jobs/runs/42/cancel', {})
  })

  it('fetchDispatcherStatus 走只读端点', async () => {
    apiV2.get.mockResolvedValue({ success: true })
    await fetchDispatcherStatus()
    expect(apiV2.get).toHaveBeenCalledWith('/jobs/dispatcher/status')
  })

  it('code / id 含特殊字符时 encodeURIComponent 生效', async () => {
    apiV2.post.mockResolvedValue({ success: true })
    apiV2.delete.mockResolvedValue({ success: true })
    await runNow('a/b c?d')
    expect(apiV2.post).toHaveBeenCalledWith('/jobs/a%2Fb%20c%3Fd/run-now', {})
    await deleteTrigger('x/y')
    expect(apiV2.delete).toHaveBeenCalledWith('/jobs/triggers/x%2Fy')
  })
})