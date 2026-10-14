import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn() },
  apiV2: { get: vi.fn(), post: vi.fn() }
}))

import { apiV2 } from '@/utils/httpClient'
import { fetchSchedulerStatus, runSchedulerJob } from '../schedulerService'

describe('schedulerService', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetchSchedulerStatus 打 /schedulers/status', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { paused: false, maintenance: {}, platform: {} } })
    await fetchSchedulerStatus()
    expect(apiV2.get).toHaveBeenCalledWith('/schedulers/status')
  })

  it('runSchedulerJob 用 POST 并带空 body', async () => {
    apiV2.post.mockResolvedValue({ success: true, message: 'Job abc triggered' })
    await runSchedulerJob('abc')
    expect(apiV2.post).toHaveBeenCalledWith('/schedulers/abc/run-now', {})
  })

  it('code 含特殊字符时 encodeURIComponent 生效', async () => {
    apiV2.post.mockResolvedValue({ success: true })
    await runSchedulerJob('a/b c?d')
    expect(apiV2.post).toHaveBeenCalledWith('/schedulers/a%2Fb%20c%3Fd/run-now', {})
  })
})
