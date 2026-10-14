import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('@/services/schedulerService', () => ({
  fetchSchedulerStatus: vi.fn(),
  runSchedulerJob: vi.fn()
}))

import { fetchSchedulerStatus, runSchedulerJob } from '@/services/schedulerService'
import PlatformOpsJobs from '../PlatformOpsJobs.vue'

// PageShell 依赖 useRouter()，提供一个内存路由避免 injection 告警
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div />' } }]
})

const NORMAL = {
  success: true,
  data: {
    paused: false,
    maintenance: {
      'cleanup-tmp': { schedule: '0 3 * * *', next_run_at: '2026-10-15T03:00:00', handler_registered: true, enabled: true },
      'rotate-log': { schedule: '0 4 * * *', next_run_at: null, handler_registered: false, enabled: false }
    },
    platform: {
      'heartbeat': { schedule: '*/1 * * * *', next_run_at: '2026-10-14T00:01:00', handler_registered: true, enabled: true }
    }
  }
}

function mountPage() {
  return mount(PlatformOpsJobs, { global: { plugins: [router] } })
}

describe('PlatformOpsJobs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('正常态：渲染运维/平台两张表与全部行', async () => {
    fetchSchedulerStatus.mockResolvedValue(NORMAL)
    const w = mountPage()
    await flushPromises()

    expect(w.find('[data-test="ops-loading"]').exists()).toBe(false)
    expect(w.find('[data-test="ops-error"]').exists()).toBe(false)
    // 2(运维) + 1(平台) 行
    expect(w.findAll('[data-test="ops-row"]').length).toBe(3)
    expect(w.text()).toContain('运维作业')
    expect(w.text()).toContain('平台作业')
    expect(w.text()).toContain('cleanup-tmp')
    expect(w.text()).toContain('heartbeat')
    expect(w.findAll('[data-test="ops-run-now"]').length).toBe(3)
  })

  it('暂停态：显示暂停提示且不渲染表格', async () => {
    fetchSchedulerStatus.mockResolvedValue({ success: true, data: { paused: true, maintenance: null, platform: null } })
    const w = mountPage()
    await flushPromises()

    expect(w.find('[data-test="ops-paused"]').exists()).toBe(true)
    expect(w.findAll('[data-test="ops-row"]').length).toBe(0)
  })

  it('空组：对应卡片内用 EmptyState 显示暂无作业', async () => {
    fetchSchedulerStatus.mockResolvedValue({
      success: true,
      data: { paused: false, maintenance: {}, platform: { heartbeat: { schedule: '* * * * *', next_run_at: null, handler_registered: true, enabled: true } } }
    })
    const w = mountPage()
    await flushPromises()

    expect(w.findAll('[data-test="ops-empty"]').length).toBe(1)
    expect(w.findAll('[data-test="ops-row"]').length).toBe(1)
  })

  it('失败（含未接线 503）：显示错误文本', async () => {
    fetchSchedulerStatus.mockResolvedValue({ success: false, message: 'in-process schedulers not initialized' })
    const w = mountPage()
    await flushPromises()

    expect(w.find('[data-test="ops-error"]').exists()).toBe(true)
    expect(w.find('[data-test="ops-error"]').text()).toContain('in-process schedulers not initialized')
  })

  it('点击「立即执行」调用 runSchedulerJob(code) 并触发一次重新拉取', async () => {
    fetchSchedulerStatus.mockResolvedValue(NORMAL)
    runSchedulerJob.mockResolvedValue({ success: true, message: 'Job cleanup-tmp triggered' })

    const w = mountPage()
    await flushPromises()
    expect(fetchSchedulerStatus).toHaveBeenCalledTimes(1)

    await w.find('[data-test="ops-run-now"]').trigger('click')
    await flushPromises()

    expect(runSchedulerJob).toHaveBeenCalledWith('cleanup-tmp')
    expect(fetchSchedulerStatus).toHaveBeenCalledTimes(2)
  })
})
