import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

// 展开原模块以保留 TaskDetailDrawer 依赖的其它导出，仅覆盖需要断言的函数
vi.mock('@/services/taskService', async (orig) => {
  const actual = await orig()
  return {
    ...actual,
    fetchTasks: vi.fn(),
    fetchWorkflowSchedules: vi.fn()
  }
})

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ user: { user_id: 'u-tester' } })
}))

import { fetchTasks, fetchWorkflowSchedules } from '@/services/taskService'
import TaskCenter from '../TaskCenter.vue'

const SCHEDULE = {
  workflow_key: 'wf-daily',
  name: '每日巡检',
  cron: '0 8 * * *',
  cron_label: '每天 08:00',
  next_run_at: '2026-10-15T08:00:00',
  node_count: 3,
  runs: []
}

describe('TaskCenter 「调度」tab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    fetchTasks.mockResolvedValue({ success: true, data: { items: [], total: 0 } })
    fetchWorkflowSchedules.mockResolvedValue({ success: true, data: { items: [SCHEDULE] } })
  })

  it('挂载默认走「监控」tab，不拉调度', async () => {
    const w = mount(TaskCenter)
    await flushPromises()
    expect(fetchTasks).toHaveBeenCalled()
    expect(fetchWorkflowSchedules).not.toHaveBeenCalled()
  })

  it('切到「调度」tab 调用 fetchWorkflowSchedules 并渲染 schedule-row', async () => {
    const w = mount(TaskCenter)
    await flushPromises()

    const scheduleTab = w.findAll('.sub-nav-tab').find(b => b.text().includes('调度'))
    expect(scheduleTab).toBeTruthy()
    await scheduleTab.trigger('click')
    await flushPromises()

    expect(fetchWorkflowSchedules).toHaveBeenCalledTimes(1)
    const rows = w.findAll('[data-test="schedule-row"]')
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('每日巡检')
  })
})
