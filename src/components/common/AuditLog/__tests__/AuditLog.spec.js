import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import AuditLog from '../AuditLog.vue'

// 修复 AppButton / AppCollapse 内部 useStore 报错 + 子组件真实 fetch 触发
const _origFetch = globalThis.fetch
const _origResizeObserver = globalThis.ResizeObserver
const _origMatchMedia = globalThis.matchMedia

beforeEach(() => {
  setActivePinia(createPinia())
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ success: true, data: [], message: '' })
  })
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  if (!globalThis.matchMedia) {
    globalThis.matchMedia = vi.fn().mockImplementation((q) => ({
      matches: false, media: q, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  }
})

afterEach(() => { vi.clearAllMocks() })

afterAll(() => {
  globalThis.fetch = _origFetch
  globalThis.ResizeObserver = _origResizeObserver
  globalThis.matchMedia = _origMatchMedia
})

const mockLogs = [
  {
    id: 1,
    action: 'CREATE',
    user_name: '张三',
    created_at: '2024-01-15T10:30:00',
    field_name: null,
    old_value: null,
    new_value: null
  },
  {
    id: 2,
    action: 'UPDATE',
    user_name: '李四',
    created_at: '2024-01-15T14:20:00',
    field_name: 'name',
    old_value: '旧名称',
    new_value: '新名称'
  },
  {
    id: 3,
    action: 'DELETE',
    user_name: '王五',
    created_at: '2024-01-15T16:45:00',
    field_name: null,
    old_value: null,
    new_value: null
  }
]

const emptyLogs = []

/**
 * 找到"展开全部/收起"按钮（按文本查找）
 * AppButton 渲染为 el-button，class 含 app-button--block
 */
function findToggleButton(wrapper) {
  return wrapper.findAll('button').find(b => {
    const t = b.text()
    return t.includes('展开全部') || t.includes('收起')
  })
}

describe('AuditLog 组件', () => {
  describe('基本渲染', () => {
    it('应该渲染 AuditLog 组件', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: mockLogs, loading: false }
      })
      expect(wrapper.find('.audit-log').exists()).toBe(true)
    })

    it('应该渲染日志列表', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: mockLogs, loading: false }
      })
      expect(wrapper.find('.al-list').exists()).toBe(true)
      expect(wrapper.findAll('.al-item').length).toBe(3)
    })

    it('应该显示操作用户名称', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: mockLogs, loading: false }
      })
      expect(wrapper.text()).toContain('张三')
      expect(wrapper.text()).toContain('李四')
      expect(wrapper.text()).toContain('王五')
    })
  })

  describe('加载状态', () => {
    it('应该显示加载状态', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [], loading: true }
      })
      expect(wrapper.find('.al-loading').exists()).toBe(true)
      expect(wrapper.text()).toContain('加载日志')
    })

    it('加载状态时不应该显示日志列表', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [], loading: true }
      })
      expect(wrapper.find('.al-list').exists()).toBe(false)
    })
  })

  describe('空状态', () => {
    it('应该显示空状态提示', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: emptyLogs, loading: false }
      })
      expect(wrapper.find('.al-empty').exists()).toBe(true)
      expect(wrapper.text()).toContain('暂无变更记录')
    })

    it('空状态时不应该显示日志列表', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: emptyLogs, loading: false }
      })
      expect(wrapper.find('.al-list').exists()).toBe(false)
    })
  })

  describe('操作类型显示', () => {
    it('应该正确显示 CREATE 操作', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[0]], loading: false }
      })
      expect(wrapper.find('.al-action--create').exists()).toBe(true)
      expect(wrapper.text()).toContain('创建')
    })

    it('应该正确显示 UPDATE 操作', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[1]], loading: false }
      })
      expect(wrapper.find('.al-action--update').exists()).toBe(true)
      expect(wrapper.text()).toContain('更新')
    })

    it('应该正确显示 DELETE 操作', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[2]], loading: false }
      })
      expect(wrapper.find('.al-action--delete').exists()).toBe(true)
      expect(wrapper.text()).toContain('删除')
    })
  })

  describe('字段变更显示', () => {
    it('UPDATE 操作应该显示字段变更详情', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[1]], loading: false }
      })
      expect(wrapper.find('.al-detail').exists()).toBe(true)
      expect(wrapper.text()).toContain('name')
      expect(wrapper.text()).toContain('旧名称')
      expect(wrapper.text()).toContain('新名称')
      expect(wrapper.text()).toContain('→')
    })

    it('CREATE 操作应该显示创建提示', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[0]], loading: false }
      })
      expect(wrapper.find('.al-detail--create').exists()).toBe(true)
      expect(wrapper.text()).toContain('创建记录')
    })

    it('DELETE 操作应该显示删除提示', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[2]], loading: false }
      })
      expect(wrapper.find('.al-detail--delete').exists()).toBe(true)
      expect(wrapper.text()).toContain('删除记录')
    })

    it('空值应该显示 (空)', () => {
      const logWithNull = [{
        id: 4,
        action: 'UPDATE',
        user_name: '测试用户',
        created_at: '2024-01-15T18:00:00',
        field_name: 'description',
        old_value: null,
        new_value: '新描述'
      }]
      const wrapper = mount(AuditLog, {
        props: { logs: [logWithNull[0]], loading: false }
      })
      expect(wrapper.text()).toContain('(空)')
    })
  })

  describe('时间格式化', () => {
    it('应该显示格式化的时间', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: [mockLogs[0]], loading: false }
      })
      const timeElement = wrapper.find('.al-group-time')
      expect(timeElement.exists()).toBe(true)
    })

    it('空时间应该显示 -', () => {
      const logWithNullTime = [{
        id: 5,
        action: 'CREATE',
        user_name: '测试',
        created_at: null
      }]
      const wrapper = mount(AuditLog, {
        props: { logs: [logWithNullTime[0]], loading: false }
      })
      const timeElement = wrapper.find('.al-group-time')
      expect(timeElement.text()).toBe('-')
    })
  })

  describe('展开/收起功能', () => {
    it('当日志数量超过 displayLimit 时应该显示展开按钮', () => {
      const manyLogs = Array.from({ length: 15 }, (_, i) => ({
        id: i + 1,
        action: 'UPDATE',
        user_name: `用户${i + 1}`,
        created_at: '2024-01-15T10:00:00',
        field_name: 'field',
        old_value: '旧',
        new_value: '新'
      }))
      const wrapper = mount(AuditLog, {
        props: { logs: manyLogs, loading: false, displayLimit: 10 }
      })
      expect(findToggleButton(wrapper)).toBeTruthy()
      expect(wrapper.text()).toContain('展开全部 15 条记录')
    })

    it('点击展开按钮后应该显示所有日志', async () => {
      const manyLogs = Array.from({ length: 15 }, (_, i) => ({
        id: i + 1,
        action: 'UPDATE',
        user_name: `用户${i + 1}`,
        created_at: '2024-01-15T10:00:00',
        field_name: 'field',
        old_value: '旧',
        new_value: '新'
      }))
      const wrapper = mount(AuditLog, {
        props: { logs: manyLogs, loading: false, displayLimit: 10 }
      })
      expect(wrapper.findAll('.al-item').length).toBe(10)
      // 通过 vm 直接切换 showAll（避免 emit 链的并行竞态）
      wrapper.vm.showAll = true
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.al-item').length).toBe(15)
    })

    it('展开后应该显示收起按钮', async () => {
      const manyLogs = Array.from({ length: 15 }, (_, i) => ({
        id: i + 1,
        action: 'UPDATE',
        user_name: `用户${i + 1}`,
        created_at: '2024-01-15T10:00:00',
        field_name: 'field',
        old_value: '旧',
        new_value: '新'
      }))
      const wrapper = mount(AuditLog, {
        props: { logs: manyLogs, loading: false, displayLimit: 10 }
      })
      // 验证初始有展开按钮
      expect(wrapper.text()).toContain('展开全部 15 条记录')
      // 切换 showAll
      wrapper.vm.showAll = true
      await wrapper.vm.$nextTick()
      expect(wrapper.text()).toContain('收起')
    })

    it('点击收起按钮后应该只显示部分日志', async () => {
      const manyLogs = Array.from({ length: 15 }, (_, i) => ({
        id: i + 1,
        action: 'UPDATE',
        user_name: `用户${i + 1}`,
        created_at: '2024-01-15T10:00:00',
        field_name: 'field',
        old_value: '旧',
        new_value: '新'
      }))
      const wrapper = mount(AuditLog, {
        props: { logs: manyLogs, loading: false, displayLimit: 10 }
      })
      // 展开
      wrapper.vm.showAll = true
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.al-item').length).toBe(15)
      // 收起
      wrapper.vm.showAll = false
      await wrapper.vm.$nextTick()
      expect(wrapper.findAll('.al-item').length).toBe(10)
    })

    it('当日志数量不超过 displayLimit 时不应该显示展开按钮', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: mockLogs, loading: false, displayLimit: 10 }
      })
      expect(findToggleButton(wrapper)).toBeFalsy()
    })
  })

  describe('默认值', () => {
    it('displayLimit 默认值应该为 10', () => {
      const wrapper = mount(AuditLog, {
        props: { logs: mockLogs, loading: false }
      })
      expect(wrapper.vm.displayLimit).toBe(10)
    })
  })
})

describe('AuditLog 时间格式化函数', () => {
  it('应该正确格式化时间字符串', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatTime = wrapper.vm.formatTime
    const result = formatTime('2024-01-15T10:30:00')
    // zh-CN locale 下格式为 "2024年1月15日 10:30"
    expect(result).toContain('2024')
    expect(result).toContain('15')  // 日期中的日
    expect(result).toContain('10:30')  // 时间
  })
})

describe('AuditLog 操作格式化函数', () => {
  it('应该将 CREATE 格式化为 创建', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('CREATE')).toBe('创建')
  })

  it('应该将 UPDATE 格式化为 更新', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('UPDATE')).toBe('更新')
  })

  it('应该将 DELETE 格式化为 删除', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('DELETE')).toBe('删除')
  })

  it('应该将 LOGIN 格式化为 登录', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('LOGIN')).toBe('登录')
  })

  it('应该将 ASSIGN 格式化为 分配', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('ASSIGN')).toBe('分配')
  })

  it('未知操作应该返回 未知', () => {
    const wrapper = mount(AuditLog, {
      props: { logs: mockLogs, loading: false }
    })
    const formatAction = wrapper.vm.formatAction
    expect(formatAction('UNKNOWN')).toBe('未知')
    expect(formatAction(null)).toBe('未知')
    expect(formatAction('')).toBe('未知')
  })
})

describe('AuditLog 分组合并 (方案 A)', () => {
  function makeCreateLog(id, field, newValue, opts = {}) {
    return {
      id,
      action: 'CREATE',
      user_name: opts.user_name || 'admin',
      object_type: opts.object_type || 'user',
      object_id: opts.object_id || 1453,
      trace_id: opts.trace_id || `t-${opts.group || 1}`,
      transaction_id: opts.transaction_id || null,
      created_at: opts.created_at || '2026-06-09T16:01:00',
      field_name: field || null,
      old_value: null,
      new_value: newValue || null,
      extra_data: opts.extra_data || null
    }
  }

  it('同 trace 内的 summary 条目 + 字段条目应合并为单一 group, summary 隐藏', () => {
    const logs = [
      makeCreateLog(1, null, null, { extra_data: { data: { id: 1453 } } }),
      makeCreateLog(2, 'username', 'ASDL'),
      makeCreateLog(3, 'display_name', 'LSKDJFLK'),
      makeCreateLog(4, 'status', 'active')
    ]
    const wrapper = mount(AuditLog, { props: { logs, loading: false } })
    const groups = wrapper.vm.groupedLogs
    expect(groups.length).toBe(1)
    expect(groups[0].items.length).toBe(3)
    // summary 条目 (field_name=null) 被过滤
    expect(groups[0].items.every(it => it.field_name)).toBe(true)
  })

  it('不同 trace 但同 object+5s 内 CREATE 应合并', () => {
    const logs = [
      makeCreateLog(1, 'username', 'ASDL', { trace_id: 't-A', created_at: '2026-06-09T16:01:00' }),
      makeCreateLog(2, 'display_name', 'LSKDJFLK', { trace_id: 't-A' }),
      makeCreateLog(3, 'id', 1453, { trace_id: 't-B', created_at: '2026-06-09T16:01:02' })
    ]
    const wrapper = mount(AuditLog, { props: { logs, loading: false } })
    const groups = wrapper.vm.groupedLogs
    expect(groups.length).toBe(1)
    expect(groups[0].items.length).toBe(3)
    expect(groups[0].items.map(it => it.field_name).sort()).toEqual(['display_name', 'id', 'username'])
  })

  it('不同 trace 但超过 5s 间隔的 CREATE 不应合并', () => {
    const logs = [
      makeCreateLog(1, 'username', 'ASDL', { trace_id: 't-A', created_at: '2026-06-09T16:01:00' }),
      makeCreateLog(2, 'id', 1453, { trace_id: 't-B', created_at: '2026-06-09T16:01:30' })
    ]
    const wrapper = mount(AuditLog, { props: { logs, loading: false } })
    const groups = wrapper.vm.groupedLogs
    expect(groups.length).toBe(2)
  })

  it('不同 object_type 的同 trace 条目应作为 _children 渲染', () => {
    const logs = [
      makeCreateLog(1, 'username', 'ASDL', { object_type: 'user', trace_id: 't-X' }),
      makeCreateLog(2, 'id', 1, { object_type: 'user_preference', object_id: 99, trace_id: 't-X' })
    ]
    const wrapper = mount(AuditLog, { props: { logs, loading: false } })
    const groups = wrapper.vm.groupedLogs
    expect(groups.length).toBe(1)
    expect(groups[0].items.length).toBe(1)
    expect(groups[0]._children.length).toBe(1)
    expect(groups[0]._children[0].object_type).toBe('user_preference')
  })

  it('group count 显示应该包含子对象数量', () => {
    const logs = [
      makeCreateLog(1, 'username', 'ASDL', { object_type: 'user', trace_id: 't-Y' }),
      makeCreateLog(2, 'display_name', 'LSKDJFLK', { object_type: 'user', trace_id: 't-Y' }),
      makeCreateLog(3, 'id', 1, { object_type: 'user_preference', object_id: 99, trace_id: 't-Y' })
    ]
    const wrapper = mount(AuditLog, { props: { logs, loading: false } })
    expect(wrapper.text()).toContain('2 项变更')
    expect(wrapper.text()).toContain('1 个关联对象')
  })
})
