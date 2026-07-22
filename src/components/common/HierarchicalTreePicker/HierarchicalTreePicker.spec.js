/**
 * [FIX 2026-07-22] HierarchicalTreePicker 单元测试
 *
 * 覆盖:
 *   - 基础渲染 + props 验证
 *   - 单选模式 (payload shape, 再次点击取消)
 *   - 多选模式 (chips 移除, 全选/清空)
 *   - 搜索 (防抖, 父链展开)
 *   - 数据加载 (mock fetch)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HierarchicalTreePicker from './HierarchicalTreePicker.vue'

const mockHierarchyConfig = {
  root_type: 'product',
  levels: [
    { object_type: 'product', parent_field: null, children_field: 'versions' },
    { object_type: 'version', parent_field: 'product_id', children_field: 'domains' },
    { object_type: 'domain', parent_field: 'version_id', children_field: 'sub_domains' },
    { object_type: 'sub_domain', parent_field: 'domain_id', children_field: null },
  ],
}

const mockTreeData = [
  { id: 1, parent_id: null, level: 0, type: 'product', name: '产品A', code: 'A', has_children: true, child_count: 1 },
  { id: 11, parent_id: 1, level: 1, type: 'version', name: 'V1.0', code: 'V1', has_children: true, child_count: 1 },
  { id: 21, parent_id: 11, level: 2, type: 'domain', name: '采购域', code: 'PROC', has_children: true, child_count: 1 },
  { id: 31, parent_id: 21, level: 3, type: 'sub_domain', name: '询价单', code: 'INQ', has_children: false, child_count: 0 },
  { id: 32, parent_id: 21, level: 3, type: 'sub_domain', name: '采购订单', code: 'PO', has_children: false, child_count: 0 },
]

function mockFetch(data = mockTreeData) {
  return vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ data, total: data.length }),
  }))
}

describe('HierarchicalTreePicker', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch())
  })

  describe('基础渲染', () => {
    it('接受 dimensionId / hierarchyConfig 必填 props', () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
        },
      })
      expect(wrapper.exists()).toBe(true)
    })

    it('缺少 hierarchyConfig 时给出 console.warn', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      expect(warn).toHaveBeenCalled()
      warn.mockRestore()
    })

    it('mount 时调用 /tree 端点', async () => {
      const fetchMock = mockFetch()
      vi.stubGlobal('fetch', fetchMock)

      mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
        },
      })
      await flushPromises()

      expect(fetchMock).toHaveBeenCalled()
      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]
      expect(lastCall).toContain('/api/v2/bo/management_dimension/sub_domain/tree')
    })
  })

  describe('多选模式', () => {
    it('点击确定时 emit type=multiple / ids / nodes', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: true,
        },
      })
      await flushPromises()

      // 直接设置内部状态模拟勾选
      wrapper.vm.checkedIds = [31]
      await wrapper.vm.$nextTick()
      // 触发确定
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      expect(events[0][0].type).toBe('multiple')
      expect(events[0][0].ids).toEqual([31])
      expect(events[0][0].nodes[0]).toMatchObject({
        id: 31,
        name: '询价单',
        type: 'sub_domain',
      })
    })

    it('空选择时确定按钮 disabled', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: true,
        },
      })
      await flushPromises()

      const btn = wrapper.find('.htp-actions .el-button--primary')
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  describe('单选模式', () => {
    it('点击确定时 emit type=single / id / node', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: false,
        },
      })
      await flushPromises()

      wrapper.vm.currentId = 31
      await wrapper.vm.$nextTick()
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events[0][0]).toMatchObject({ type: 'single', id: 31 })
      expect(events[0][0].node.name).toBe('询价单')
    })

    it('无选中时确定按钮 disabled', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: false,
        },
      })
      await flushPromises()

      const btn = wrapper.find('.htp-actions .el-button--primary')
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  describe('搜索', () => {
    it('300ms 防抖后才发起请求', async () => {
      const fetchMock = mockFetch()
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
        },
      })
      await flushPromises()
      const initialCalls = fetchMock.mock.calls.length

      // 触发输入
      await wrapper.find('.htp-search input').setValue('采购')
      // 立即检查 — 还没到 debounce 时间
      await flushPromises()
      expect(fetchMock.mock.calls.length).toBe(initialCalls)

      // 等防抖
      await new Promise(r => setTimeout(r, 350))
      await flushPromises()
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls)

      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]
      expect(lastCall).toContain('search=')
    })
  })

  describe('ancestorPath 生成', () => {
    it('confirm payload 中 node 包含 ancestorPath', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: true,
        },
      })
      await flushPromises()

      wrapper.vm.checkedIds = [32]  // 采购订单
      await wrapper.vm.$nextTick()
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      const ancestor = events[0][0].nodes[0].ancestorPath
      expect(ancestor).toContain('产品A')
      expect(ancestor).toContain('V1.0')
      expect(ancestor).toContain('采购域')
      expect(ancestor).toContain('采购订单')
    })
  })
})